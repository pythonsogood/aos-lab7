import time
from typing import NamedTuple

from hypervisor import Hypervisor


GUEST_USERNAME = "user"
GUEST_PASSWORD = ""


class ExecutableInfo(NamedTuple):
	executable: str
	args: tuple[str, ...]


def choose_executable(vm_os: str) -> ExecutableInfo:
	os_name = vm_os.lower()

	if "windows" in os_name:
		return ExecutableInfo(executable=r"C:\Windows\System32\notepad.exe", args=())

	return ExecutableInfo(executable="/bin/sleep", args=("60",))


def main() -> None:
	hv = Hypervisor(1, "Hypervisor1")

	machine_names = tuple(machine.name for machine in Hypervisor.VBOX.machines)

	if len(machine_names) < 2:
		raise RuntimeError("At least two VirtualBox VMs are required")

	vm1 = hv.create_vm(1, machine_names[0], GUEST_USERNAME, GUEST_PASSWORD)
	vm2 = hv.create_vm(2, machine_names[1], GUEST_USERNAME, GUEST_PASSWORD)
	vms = (vm1, vm2)

	hv.list_vms()

	for vm in vms:
		vm.show_specs()

	for vm in vms:
		vm.start_vm("gui")
		time.sleep(10)

	time.sleep(15)

	pids: dict[str, int] = {}

	for vm in vms:
		executable, args = choose_executable(vm.os)
		pid = vm.run_app(executable, args)
		pids[vm.name] = pid

	time.sleep(6) # performance monitor runs with 5 seconds interval

	for vm in vms:
		apps = ", ".join(tuple(f"{app.Name} (PID {app.PID})" for app in vm.running_apps))
		print(f"Running apps on {vm.name}: {apps}")

	time.sleep(3)

	for vm in vms:
		vm.stop_app(pids[vm.name])

	time.sleep(1)

	for vm in vms:
		vm.show_specs()

		utilization = vm.calculate_utilization()

		print(f"Resource utilization for {vm.name} - CPU: {utilization.cpu_percent:.2f}%, Memory: {utilization.memory_percent:.2f}%, Storage: {utilization.storage_percent:.2f}%")

	for vm in vms:
		vm.stop_vm()


if __name__ == "__main__":
	main()
