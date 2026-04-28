from typing import NamedTuple, TypedDict


class VirtualMachineUtilization(NamedTuple):
	cpu_percent: float
	memory_percent: float
	storage_percent: float


class VirtualMachineRunningApp(TypedDict):
	name: str
	cpu: int
	memory: int
	storage: int


class VirtualMachine:
	def __init__(self, id: int, name: str, cpu: int, memory: int, storage: int) -> None:
		self.__id = id
		self.__name = name

		self.__total_cpu = cpu
		self.__total_memory = memory
		self.__total_storage = storage

		self.__available_cpu = cpu
		self.__available_memory = memory
		self.__available_storage = storage

		self.__running_apps: list[VirtualMachineRunningApp] = []

	@property
	def id(self) -> int:
		return self.__id

	@property
	def name(self) -> str:
		return self.__name

	@property
	def total_cpu(self) -> int:
		return self.__total_cpu

	@property
	def total_memory(self) -> int:
		return self.__total_memory

	@property
	def total_storage(self) -> int:
		return self.__total_storage

	@property
	def available_cpu(self) -> int:
		return self.__available_cpu

	@property
	def available_memory(self) -> int:
		return self.__available_memory

	@property
	def available_storage(self) -> int:
		return self.__available_storage

	@property
	def running_apps(self) -> tuple[VirtualMachineRunningApp, ...]:
		return tuple(self.__running_apps)

	def run_app(self, app: str, cpu: int, memory: int, storage: int) -> None:
		if (cpu <= self.__available_cpu and
			memory <= self.__available_memory and
			storage <= self.__available_storage):

			self.__running_apps.append(VirtualMachineRunningApp(
				name=app,
				cpu=cpu,
				memory=memory,
				storage=storage
			))

			self.__available_cpu -= cpu
			self.__available_memory -= memory
			self.__available_storage -= storage

			print(f"Running {app} on {self.__name}")
		else:
			print(f"Error: Not enough resources to run {app} on {self.__name}")

	def stop_app(self, app: str) -> None:
		for application in self.__running_apps:
			if application["name"] == app:
				self.__running_apps.remove(application)

				self.__available_cpu += application["cpu"]
				self.__available_memory += application["memory"]
				self.__available_storage += application["storage"]

				print(f"Stopped {app} on {self.__name}. Freed up CPU: {application['cpu']}, Memory: {application['memory']}, Storage: {application['storage']}")
				break
		else:
			print(f"Error: {app} not found on {self.__name}")

	def show_specs(self) -> None:
		print(f"""VM Name: {self.__name}, CPU: {self.__available_cpu}/{self.__total_cpu},
Memory: {self.__available_memory}/{self.__total_memory},
Storage: {self.__available_storage}/{self.__total_storage}""")

	def calculate_utilization(self, cpu: int, memory: int, storage: int) -> VirtualMachineUtilization:
		cpu_percent = (cpu / self.__total_cpu) * 100
		memory_percent = (memory / self.__total_memory) * 100
		storage_percent = (storage / self.__total_storage) * 100

		return VirtualMachineUtilization(cpu_percent, memory_percent, storage_percent)
