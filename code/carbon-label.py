import subprocess
import time
import threading
from itertools import cycle
from prometheus_client import start_http_server, Gauge

# --- 24-HOUR / 12-MINUTES ---
# Each step = 10 seconds of demo = 20 minutes of real time.
# Total 72 steps = 24 hours.
REGION_CONFIG = {
    "region-asia-east": [
        300, 280, 260, 240, 220, 200, 180, 160, 140, 120, 110, 100,  # 00:00 - 04:00
        90, 85, 80, 85, 90, 95, 100, 110, 120, 130, 140, 150,       # 04:00 - 08:00
        160, 170, 180, 190, 200, 210, 220, 230, 240, 250, 260, 270,  # 08:00 - 12:00
        280, 300, 320, 340, 360, 380, 400, 420, 440, 460, 480, 500,  # 12:00 - 16:00
        480, 460, 440, 420, 400, 380, 360, 340, 320, 300, 280, 260,  # 16:00 - 20:00
        240, 220, 200, 190, 180, 170, 180, 190, 200, 210, 220, 230  # 20:00 - 00:00
    ],
    "region-eu-west": [
        100, 105, 110, 115, 120, 125, 130, 140, 150, 160, 170, 180,  # 00:00 - 04:00
        250, 350, 450, 500, 500, 500, 500, 500, 500, 500, 500, 480,  # 04:00 - 08:00
        460, 440, 420, 400, 380, 360, 340, 320, 300, 280, 260, 240,  # 08:00 - 12:00
        220, 200, 180, 160, 140, 120, 100, 90, 80, 75, 80, 90,  # 12:00 - 16:00
        100, 120, 150, 180, 210, 240, 270, 300, 330, 360, 390, 420,  # 16:00 - 20:00
        450, 420, 380, 340, 300, 260, 220, 180, 140, 120, 110, 100  # 20:00 - 00:00
    ],
    "region-us-east": [
        300, 240, 230, 220, 210, 200, 190, 180, 170, 160, 150, 140,  # 00:00 - 04:00
        130, 120, 110, 100, 95, 90, 85, 80, 75, 80, 85, 90,  # 04:00 - 08:00
        95, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200,  # 08:00 - 12:00
        220, 240, 260, 280, 300, 320, 340, 360, 380, 400, 420, 440,  # 12:00 - 16:00
        460, 480, 500, 500, 500, 500, 480, 460, 440, 420, 400, 380,  # 16:00 - 20:00
        360, 340, 320, 300, 280, 260, 240, 220, 200, 180, 160, 140  # 20:00 - 00:00
    ]
}

dummy_cycles = {k: cycle(v) for k, v in REGION_CONFIG.items()}
CARBON_INTENSITY = Gauge('carbon_intensity_gco2',
                         'Carbon intensity in gCO2/kWh', ['region'])
current_values = {k: 0 for k in REGION_CONFIG.keys()}


def update_metrics_loop():
  while True:
    for region in REGION_CONFIG.keys():
      value = next(dummy_cycles[region])
      CARBON_INTENSITY.labels(region=region).set(value)
      current_values[region] = value
    time.sleep(5)


def k8s_labeler_loop():
  step = 0
  while step <= 71:
    total_minutes = step * 20
    sim_hours = (total_minutes // 60) % 24
    sim_mins = total_minutes % 60
    time_str = f"{sim_hours:02d}:{sim_mins:02d}"

    print("\n" + "=" * 50)
    print(f"GLOBAL GRID SYNC | Simulated Time: {time_str}")
    print("=" * 50)

    for region, value in current_values.items():
      if value == 0:
        continue
      cmd = ["kubectl", "label", "namespace", region,
             f"carbon-intensity={value}", "--overwrite"]
      try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=5)
        status = "[GREEN]" if value < 200 else "[MEDIUM]  " if value < 400 else "[HIGH] "
        print(f"[{status}] {region:16} -> {value} gCO2/kWh")
      except Exception as e:
        print(f"[ERROR] Error labelling {region}: {e}")

    step += 1
    time.sleep(10)


if __name__ == '__main__':
  start_http_server(8000, addr='0.0.0.0')
  print(f"[STARTED] Prometheus Exporter active on port 8000")
  threading.Thread(target=update_metrics_loop, daemon=True).start()
  threading.Thread(target=k8s_labeler_loop, daemon=True).start()
  try:
    while True:
      time.sleep(1)
  except KeyboardInterrupt:
    print("\nSimulation stopped.")
