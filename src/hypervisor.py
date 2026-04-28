from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .virtual_machine import VirtualMachine


class Hypervisor:
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

	def create_vm(self, vm):
		self.__vms.append(vm)
		print(f"Created VM {vm.name} on {self.name}")

	def remove_vm(self, vm):
		if vm in self.__vms:
			self.__vms.remove(vm)
			print(f"Removed VM {vm.name} from {self.name}")
		else:
			print(f"VM {vm.name} not found on {self.name}")

	def list_vms(self):
		for vm in self.__vms:
			print(f"VM ID: {vm.id}, VM Name: {vm.name}")
