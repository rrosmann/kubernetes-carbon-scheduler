import time
from kubernetes import client, config

SCHEDULER_NAME = "carbon-scheduler"

config.load_kube_config()
v1 = client.CoreV1Api()


def inject(name, priority, app_type):
  pod_manifest = {
      "apiVersion": "v1",
      "kind": "Pod",
      "metadata": {
          "name": name,
          "labels": {
              "priority": priority,
              "app": app_type
          }
      },
      "spec": {
          "schedulerName": SCHEDULER_NAME,
          "containers": [{
              "name": "worker",
              "image": "busybox",
              "command": ["sleep", "infinity"]
          }]
      }
  }

  try:
    v1.create_namespaced_pod(namespace="default", body=pod_manifest)
    print(f"[STARTING] Injected {name} | Priority: {priority} | App: {app_type}")
  except Exception as e:
    print(f"[ERROR] Failed to inject {name}: {e}")


if __name__ == "__main__":
  print("[STARTING] Starting Workload Injection (Persistent Mode)...")

  for i in range(3):
    inject(f"sim-app-{i}", "critical", "main-app")

  time.sleep(3)

  for i in range(4):
    inject(f"sim-job-{i}", "medium", "worker")

  time.sleep(3)

  for i in range(2):
    inject(f"sim-burst-{i}", "low", "worker")

  print("\n[DONE] All workloads injected.")
