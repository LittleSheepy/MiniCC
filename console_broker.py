import threading


class ConsoleBroker:
    """Serialize normal prompts and worker permission questions on one stdin."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reader = None

    def ask(self, prompt: str) -> str:
        with self._lock:
            return (self.reader or input)(prompt)


CONSOLE = ConsoleBroker()
