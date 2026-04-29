from typing import Any, overload

import vboxapi

from virtual_machine import VirtualMachine


class Hypervisor:
	VBOX_MANAGER = vboxapi.VirtualBoxManager()
	VBOX = VBOX_MANAGER.getVirtualBox()

	def __init__(self, id: int, name: str):
		self.__id = id
		self.__name = name
		self.__vms: list[VirtualMachine] = []

	@property
	def id(self) -> int:
		return self.__id

	@property
	def name(self) -> str:
		return self.__name

	@property
	def vms(self) -> tuple[VirtualMachine, ...]:
		return tuple(self.__vms)

	def find_machine(self, vm_name: str) -> Any | None:
		try:
			return self.__class__.VBOX.findMachine(vm_name)
		except Exception:
			return None

	def create_vm(self, id: int, name: str, username: str = "user", password: str = "") -> VirtualMachine:
		machine = self.find_machine(name)

		if machine is None:
			raise KeyError("Machine not found")

		vm = VirtualMachine(id, machine, self.__class__.VBOX_MANAGER, username, password)

		self.__vms.append(vm)
		print(f"Created VM {vm.name} on {self.name}")

		return vm

	@overload
	def remove_vm(self, *, id: int) -> None:
		...

	@overload
	def remove_vm(self, *, name: str) -> None:
		...

	def remove_vm(self, *, id: int | None = None, name: str | None = None):
		if id is None and name is None:
			raise ValueError("Either id or name must be provided")

		vm = None

		if id is not None:
			vm = next((vm for vm in self.__vms if vm.id == id), None)
		elif name is not None:
			vm = next((vm for vm in self.__vms if vm.name == name), None)

		if vm is None:
			print(f"VM not found {id or name}")
			return

		self.__vms.remove(vm)
		print(f"Removed VM {vm.name} from {self.name}")

	def list_vms(self):
		for vm in self.__vms:
			print(f"VM ID: {vm.id}, VM Name: {vm.name}")
