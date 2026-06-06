"""Helper: tee stdout to both terminal and a log file with timestamps."""
import sys, os, datetime
class Tee:
    def __init__(self, logpath):
        os.makedirs(os.path.dirname(logpath), exist_ok=True)
        self.terminal = sys.stdout
        self.log = open(logpath, 'a', encoding='utf-8')
    def write(self, msg):
        ts = datetime.datetime.now().strftime('%H:%M:%S ')
        self.terminal.write(msg)
        if msg.strip():
            self.log.write(ts + msg)
        self.flush()
    def flush(self):
        self.terminal.flush()
        self.log.flush()
# Usage: python3 -c "import logtee; logtee.Tee('logs/xxx.log')" ...
if __name__ == '__main__':
    import importlib, pathlib
    src = pathlib.Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location('mod', src)
    mod = importlib.util.module_from_spec(spec)
    sys.stdout = Tee(sys.argv[2])
    spec.loader.exec_module(mod)
