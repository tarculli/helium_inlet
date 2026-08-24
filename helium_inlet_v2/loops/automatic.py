import time

class AutomaticRunner:
    def __init__(self):
        self.enabled = False
        self.sequence = [1, 2, 3, 4]
        self.index = 0
        self.interval = 5.0
        self.last_step_time = 0.0

    def start(self):
        self.enabled = True
        self.index = 0
        self.last_step_time = 0.0  # Triggers immediately on start

    def stop(self):
        self.enabled = False

    def step(self):
        """Called inside background loop to evaluate time intervals."""
        if not self.enabled:
            return

        now = time.time()
        if now - self.last_step_time >= self.interval:
            target_state = self.sequence[self.index]
            
            # Local import prevents circular dependency on initial startup
            from state import enqueue_command
            enqueue_command({"cmd": "SET_FLOW_STATE", "state": target_state})
            
            self.index = (self.index + 1) % len(self.sequence)
            self.last_step_time = now

# Singleton instance for application access
automatic_runner = AutomaticRunner()

def run_auto_loop():
    """Thread target for main.py."""
    while True:
        automatic_runner.step()
        time.sleep(0.1)