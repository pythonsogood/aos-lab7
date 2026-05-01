import time
from hypervisor import Hypervisor


def main() -> None:
	hv = Hypervisor(1, "Hypervisor1")

	vm1 = hv.create_vm(1, "win11 24h2 iot ltsc", "user", "1")

	pid = vm1.run_app("C:\\Windows\\System32\\notepad.exe")
	print(pid)

	time.sleep(2)
	vm1.stop_app(pid)


if __name__ == "__main__":
    main()
