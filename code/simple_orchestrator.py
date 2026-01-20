import time
from kubernetes import client, config

# --- CONFIGURATION ---
SCHEDULER_NAME = "carbon-scheduler"
CAPACITY_PER_REGION = 4
HOME_REGION = "region-eu-west"  # Critical pods are pinned here

KUBECONFIGS = {
    "region-eu-west": "./kubeconfig.eu-west",
    "region-us-east": "./kubeconfig.us-east",
    "region-asia-east": "./kubeconfig.asia-east"
}

config.load_kube_config()
v1_host = client.CoreV1Api()


def get_v1_client(region_name):
  return client.CoreV1Api(config.new_client_from_config(config_file=KUBECONFIGS[region_name]))


def get_counts():
  """Returns current pod counts for each region cluster."""
  counts = {}
  for name in KUBECONFIGS.keys():
    try:
      v1_reg = get_v1_client(name)
      pods = v1_reg.list_namespaced_pod("default").items
      counts[name] = len(pods)
    except:
      counts[name] = 0
  return counts


def find_least_loaded(counts):
  candidates = sorted(counts.items(), key=lambda x: x[1])

  for name, count in candidates:
    if count < CAPACITY_PER_REGION:
      return name
  return None


def migrate_pod(pod, target_ns):
  name = pod.metadata.name
  prio = pod.metadata.labels.get("priority", "none")
  print(f"[STARTING] PLACEMENT: {name:15} ({prio:8}) -> {target_ns}")

  try:
    v1_host.delete_namespaced_pod(
      name=name, namespace="default", grace_period_seconds=0)

    pod.metadata.resource_version = None
    pod.metadata.namespace = "default"
    pod.metadata.uid = None
    pod.spec.node_name = None
    pod.spec.scheduler_name = None

    get_v1_client(target_ns).create_namespaced_pod(
      namespace="default", body=pod)
    return True
  except Exception as e:
    print(f"[ERROR] Failed to place {name}: {e}")
    return False


def reconcile():
  print(
    f"[STARTING] Simple Priority Orchestrator | Critical: {HOME_REGION} | Others: Load Balanced")
  while True:
    try:
      current_counts = get_counts()
      host_pods = v1_host.list_namespaced_pod("default").items

      pending = [p for p in host_pods if p.spec.scheduler_name == SCHEDULER_NAME]

      for pod in pending:
        prio = pod.metadata.labels.get("priority", "none").lower()

        if prio == "critical":
          if current_counts[HOME_REGION] < CAPACITY_PER_REGION:
            if migrate_pod(pod, HOME_REGION):
              current_counts[HOME_REGION] += 1

        else:
          target = find_least_loaded(current_counts)
          if target:
            if migrate_pod(pod, target):
              current_counts[target] += 1
          else:
            print(f"[ERROR] No capacity available for {pod.metadata.name}")

    except Exception as e:
      print(f"[ERROR] Loop Error: {e}")

    time.sleep(3)


if __name__ == "__main__":
  reconcile()
