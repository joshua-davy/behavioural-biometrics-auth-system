import math
from typing import List, Dict
#
class KeystrokeHandler:
    def __init__(self):
        self.reset()
# reset all lists
    def reset(self) -> None:
        self.press_times: List[float] = [] #keydown
        self.release_times: List[float] = [] #keyup
        self.keys_pressed: List[str] = [] # sequence of keys typed, for prompt ver

        self.dwell_times: List[float] = [] # keyup - keydown
        self.flight_times: List[float] = [] # keydown - keyup
        self.latency: List[float] = [] # keydown - keydown
        self.intervals: List[float] = [] # keyup - keyup

    def process_events(self, events: List[Dict]) -> None:
        self.reset()

        # sort events by time, lambda pulls t from each event for sorting
        # 0 is default to prevent crash
        events = sorted(events, key=lambda e: e.get("t", 0))

        # Dictionary mapping for key name to list of press timestamps
        # handles case where same key pressed twice before release
        press_map: Dict[str, List[float]] = {}

        for e in events:
            key = str(e.get("key", ""))
            event_type = e.get("type")
            t = float(e.get("t", 0.0)) / 1000.0

            # array comes from js and sorted by type
            if event_type == "down":
                self.press_times.append(t)
                self.keys_pressed.append(key)
                if len(self.press_times) > 1:
                    self.latency.append(t - self.press_times[-2])
                if len(self.release_times) > 0:
                    self.flight_times.append(t - self.release_times[-1])
                    # create list if key missing
                press_map.setdefault(key, []).append(t)

            elif event_type == "up":
                self.release_times.append(t)
                if len(self.release_times) > 1:
                    self.intervals.append(t - self.release_times[-2])

                    # checks if key has been pressed and if list is not empty
                if key in press_map and press_map[key]:
                    down_t = press_map[key].pop(0)
                    self.dwell_times.append(max(0.0, t - down_t))

    def dataSummary(self) -> Dict:
        def avg(values: List[float]) -> float:
            return (sum(values) / len(values)) if values else 0.0

        def stdev(values: List[float]) -> float:
            if len(values) < 2:
                return 0.0
        # bessels correction , n-1 not just n for small sample
            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
            # to account for floating point errors
            variance = max(variance, 0.0)
            return math.sqrt(variance)

        return {
            "keys": len(self.keys_pressed),

            "avg_dwell_ms": round(avg(self.dwell_times) * 1000.0, 2),
            "std_dwell_ms": round(stdev(self.dwell_times) * 1000.0, 2),

            "avg_flight_ms": round(avg(self.flight_times) * 1000.0, 2),
            "std_flight_ms": round(stdev(self.flight_times) * 1000.0, 2),

            "avg_latency_ms": round(avg(self.latency) * 1000.0, 2),
            "std_latency_ms": round(stdev(self.latency) * 1000.0, 2),

            "avg_interval_ms": round(avg(self.intervals) * 1000.0, 2),
            "std_interval_ms": round(stdev(self.intervals) * 1000.0, 2),

            "samples": {
                "dwell": len(self.dwell_times),
                "flight": len(self.flight_times),
                "latency": len(self.latency),
                "interval": len(self.intervals),
            }
        }