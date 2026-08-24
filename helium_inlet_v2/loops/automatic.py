import time
from state import enqueue_command

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
        self.last_step_time = 0.0  # Triggers step 1 immediately upon start

    def stop(self):
        self.enabled = False

    def step(self):
        """Called by background thread to evaluate time intervals."""
        if not self.enabled:
            return

        now = time.time()
        if now - self.last_step_time >= self.interval:
            target_state = self.sequence[self.index]
            
            # Enqueue command through the standard state manager
            enqueue_command({"cmd": "SET_FLOW_STATE", "state": target_state})
            
            self.index = (self.index + 1) % len(self.sequence)
            self.last_step_time = now

# Singleton instance
automatic_runner = AutomaticRunner()

def run_auto_loop():
    """Background thread target to tick the auto sequence timer."""
    while True:
        automatic_runner.step()
        time.sleep(0.1)