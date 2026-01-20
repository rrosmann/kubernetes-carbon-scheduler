import time
from kubernetes import client, config

# --- CONFIGURATION ---
SCHEDULER_NAME = "carbon-scheduler"
CAPACITY_PER_REGION = 4
HOME_REGION = "region-eu-west"
LOW_THRESHOLD = 200
MED_THRESHOLD = 400

KUBECONFIGS = {
    "region-eu-west": "./kubeconfig.eu-west",
    "region-us-east": "./kubeconfig.us-east",
    "region-asia-east": "./kubeconfig.asia-east"
}

config.load_kube_config()
v1_host = client.CoreV1Api()


def get_category(carbon):
  if carbon < LOW_THRESHOLD:
    return 1  # GREEN
  if carbon < MED_THRESHOLD:
    return 2  # YELLOW
  return 3  # RED


def get_v1_client(region_name):
  if region_name == "default":
    return v1_host
  return client.CoreV1Api(config.new_client_from_config(config_file=KUBECONFIGS[region_name]))


def get_global_status():
  regions = {}
  namespaces = v1_host.list_namespace().items
  for ns in namespaces:
    name = ns.metadata.name
    if name in KUBECONFIGS:
      carbon = int(ns.metadata.labels.get("carbon-intensity", 999))
      status = ns.metadata.labels.get("status", "Active")
      category = get_category(carbon)
      try:
        v1_v = get_v1_client(name)
        v_pods = v1_v.list_namespaced_pod("default").items
        regions[name] = {
            "carbon": carbon,
            "category": category,
            "status": status,
            "count": len(v_pods),
            "pods": v_pods
        }
      except:
        regions[name] = {"carbon": carbon, "category": 3,
                         "status": "Down", "count": 0, "pods": []}
  return regions


def migrate_pod(pod, source_ns, target_ns):
  try:
    name = pod.metadata.name
    prio = pod.metadata.labels.get("priority", "low")

    v1_src = get_v1_client(source_ns)
    v1_src.delete_namespaced_pod(
      name=name, namespace="default", grace_period_seconds=0)

    new_pod = client.V1Pod(
        metadata=client.V1ObjectMeta(
          name=name, labels=pod.metadata.labels, namespace="default"),
        spec=pod.spec
    )
    new_pod.spec.node_name = None
    new_pod.spec.scheduler_name = SCHEDULER_NAME if target_ns == "default" else None

    v1_target = get_v1_client(target_ns)
    v1_target.create_namespaced_pod(namespace="default", body=new_pod)
    print(f"[MOVED] MOVED: {name:15} | {prio:8} | {source_ns} -> {target_ns}")
    return True
  except Exception as e:
    print(f"[FAIL] Migration Fail ({name}): {e}")
    return False


def kill_for_space(region_name, count_needed):
  try:
    v1_reg = get_v1_client(region_name)
    pods = v1_reg.list_namespaced_pod("default").items
    victims = [p for p in pods if p.metadata.labels.get("priority") == "low"]
    killed = 0
    for victim in victims:
      if killed >= count_needed:
        break
      if migrate_pod(victim, region_name, "default"):
        killed += 1
    return killed
  except:
    return 0


def reconcile():
  print("🚀 Master Orchestrator | MODE: Critical-Home-Only + Sequential Priority")
  while True:
    try:
      # critical
      regions = get_global_status()
      host_pods = v1_host.list_namespaced_pod("default").items

      critical_workloads = []
      for r_name, r_info in regions.items():
        for p in r_info['pods']:
          if p.metadata.labels.get("priority") == "critical":
            critical_workloads.append((p, r_name))
      for p in host_pods:
        if p.spec.scheduler_name == SCHEDULER_NAME and p.metadata.labels.get("priority") == "critical":
          critical_workloads.append((p, "default"))

      for pod, loc in critical_workloads:
        if loc != HOME_REGION:
          if regions[HOME_REGION]['count'] >= CAPACITY_PER_REGION:
            kill_for_space(HOME_REGION, 1)
          if migrate_pod(pod, loc, HOME_REGION):
            regions = get_global_status()

      #medium 
      regions = get_global_status()
      host_pods = v1_host.list_namespaced_pod("default").items
      med_workloads = []
      for r_name, r_info in regions.items():
        for p in r_info['pods']:
          if p.metadata.labels.get("priority") == "medium":
            med_workloads.append((p, r_name))
      for p in host_pods:
        if p.spec.scheduler_name == SCHEDULER_NAME and p.metadata.labels.get("priority") == "medium":
          med_workloads.append((p, "default"))

      for pod, loc in med_workloads:
        candidates = sorted([(n, i) for n, i in regions.items() if i['status'] == "Active"],
                            key=lambda x: (x[1]['category'], x[1]['carbon']))
        curr_cat = regions[loc]['category'] if loc != "default" else 99
        for best_n, best_i in candidates:
          if best_i['category'] < curr_cat:
            if best_i['count'] < CAPACITY_PER_REGION:
              if migrate_pod(pod, loc, best_n):
                regions = get_global_status()
                break
            elif kill_for_space(best_n, 1) > 0:
              if migrate_pod(pod, loc, best_n):
                regions = get_global_status()
                break

      #low
      regions = get_global_status()
      low_workloads = []
      for r_name, r_info in regions.items():
        for p in r_info['pods']:
          if p.metadata.labels.get("priority") == "low":
            low_workloads.append((p, r_name))
      for p in v1_host.list_namespaced_pod("default").items:
        if p.spec.scheduler_name == SCHEDULER_NAME and p.metadata.labels.get("priority") == "low":
          low_workloads.append((p, "default"))

      for pod, loc in low_workloads:
        if loc != "default" and regions[loc]['category'] > 1:
          migrate_pod(pod, loc, "default")
          regions = get_global_status()
        elif loc == "default":
          green_slots = sorted([(n, i) for n, i in regions.items()
                               if i['status'] == "Active" and i['category'] == 1 and i['count'] < CAPACITY_PER_REGION],
                               key=lambda x: x[1]['carbon'])
          if green_slots:
            if migrate_pod(pod, "default", green_slots[0][0]):
              regions = get_global_status()

      summary = " | ".join(
        [f"{n}: {i['count']}/4 ({'[GREEN]' if i['category'] == 1 else '[MEDIUM]' if i['category'] == 2 else '[HIGH]'})" for n, i in regions.items()])
      print(f"[SOLUTION] {summary}")

    except Exception as e:
      print(f"[ERROR] Loop Error: {e}")
    time.sleep(4)


if __name__ == "__main__":
  reconcile()
