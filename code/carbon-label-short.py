import subprocess
import time
import threading
from itertools import cycle
from prometheus_client import start_http_server, Gauge

REGION_CONFIG = {
    "region-asia-east": [450, 350, 250, 150, 80, 150, 250, 350, 450, 500, 450, 350, 250, 150, 80, 150, 350, 450],
    "region-eu-west": [80, 150, 350, 500, 500, 350, 150, 80, 150, 250, 450, 500, 500, 350, 150, 80, 100, 120],
    "region-us-east": [250, 450, 500, 350, 150, 80, 150, 250, 350, 450, 500, 350, 150, 80, 150, 250, 350, 400]
}

dummy_cycles = {k: cycle(v) for k, v in REGION_CONFIG.items()}
CARBON_INTENSITY = Gauge('carbon_intensity_gco2', 'gCO2/kWh', ['region'])
current_values = {k: 0 for k in REGION_CONFIG.keys()}


def update_metrics_loop():
  while True:
    for region in REGION_CONFIG.keys():
      value = next(dummy_cycles[region])
      CARBON_INTENSITY.labels(region=region).set(value)
      current_values[region] = value
    time.sleep(10)


def k8s_labeler_loop():
  step = 0
  while True:
    total_minutes = step * 80
    time_str = f"{(total_minutes // 60) % 24:02d}:{total_minutes % 60:02d}"

    print(f"\n{time_str} | SYNCING GRID")
    for region, value in current_values.items():
      if value == 0:
        continue
      subprocess.run(["kubectl", "label", "namespace", region, f"carbon-intensity={value}", "--overwrite"],
                     capture_output=True, timeout=5)
      status = "[GREEN]" if value < 200 else "[MEDIUM]" if value < 400 else "[HIGH]"
      print(f"{status} {region:16} -> {value}")

    step += 1
    time.sleep(10)


if __name__ == '__main__':
  start_http_server(8000, addr='0.0.0.0')
  threading.Thread(target=update_metrics_loop, daemon=True).start()
  threading.Thread(target=k8s_labeler_loop, daemon=True).start()
  while True:
    time.sleep(1)
