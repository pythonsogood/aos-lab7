import math
import time
from threading import Thread
from typing import Any, Literal, NamedTuple, NotRequired, TypedDict

import vboxapi


type VirtualBoxFrontend = Literal["gui", "headless", "separate"]


class VirtualMachineStorageDiskInfo(NamedTuple):
	name: str
	location: str
	format: str
	used: int
	total: int


class VirtualMachineStorageInfo(NamedTuple):
	used: int
	total: int
	disks: list[VirtualMachineStorageDiskInfo]


class VirtualMachineUtilization(NamedTuple):
	cpu_percent: float
	memory_percent: float
	storage_percent: float


class VirtualMachineRunningApp(TypedDict):
	app_name: str
	process_name: int
	process_id: NotRequired[int]


class VirtualMachine:
	def __init__(self, id: int, machine: Any, manager: vboxapi.VirtualBoxManager, username: str, password: str) -> None:
		self.__id = id
		self.__machine = machine

		self.__vbox_manager = manager
		self.__vbox = manager.getVirtualBox()

		self.__guest_username = username
		self.__guest_password = password

		self.__running_apps = []

		self.__used_memory = 0

		self.__perf_monitor_state = False
		self.__perf_monitor_thread: Thread | None = None

	@property
	def id(self) -> int:
		return self.__id

	@property
	def name(self) -> str:
		return self.__machine.name

	@property
	def os(self) -> str:
		return self.__machine.OSType

	@property
	def total_cpu(self) -> int:
		return self.__machine.CPUCount

	@property
	def total_memory(self) -> int:
		return self.__machine.memorySize

	@property
	def total_storage(self) -> int:
		return self.get_virtualbox_storage_info().total

	@property
	def available_cpu(self) -> int:
		return math.floor(self.total_cpu * self.__used_cpu / 100)

	@property
	def available_memory(self) -> int:
		return self.total_memory - self.__used_memory

	@property
	def available_storage(self) -> int:
		storage_info = self.get_virtualbox_storage_info()

		return storage_info.total - storage_info.used

	@property
	def running_apps(self) -> tuple[VirtualMachineRunningApp, ...]:
		return tuple(self.__running_apps)

	def start_vm(self, frontend: VirtualBoxFrontend = "headless") -> None:
		session = self.__vbox_manager.getSessionObject(self.__vbox)
		progress = self.__machine.launchVMProcess(session, frontend, "")
		progress.waitForCompletion(-1)

		print(f"Started VM {self.name}")

		session.unlockMachine()

		self.__perf_monitor_state = True

		if self.__perf_monitor_thread is None:
			self.__perf_monitor_thread = Thread(target=self.__perf_monitor)
			self.__perf_monitor_thread.start()

	def stop_vm(self) -> None:
		self.__perf_monitor_state = False

		if (perf_thread := self.__perf_monitor_thread) is not None:
			perf_thread.join()
			self.__perf_monitor_thread = None

		session = self.__vbox_manager.getSessionObject(self.__vbox)
		self.__machine.lockMachine(session, self.__vbox_manager.constants.LockType_Shared)

		console = session.console
		progress = console.powerDown()
		progress.waitForCompletion(-1)

		print(f"Stopped VM {self.name}")

		session.unlockMachine()

	def run_app(self, app_name: str, executable: str, args: list[str] | None = None) -> None:
		if args is None:
			args = []

		session = self.__vbox_manager.getSessionObject(self.__vbox)

		try:
			self.__machine.lockMachine(session, self.__vbox_manager.constants.LockType_Shared)
			console = session.console
			guest = console.guest

			process = guest.createSession(
				self.__guest_username,
				self.__guest_password,
				"",
				f"{self.name}-guest-session",
			)

			process.waitForArray(
				(self.__vbox_manager.constants.GuestSessionWaitForFlag_Start,),
				30000,
			)

			arguments = [executable] + args
			environment_changes = []
			flags = [
				self.__vbox_manager.constants.ProcessCreateFlag_WaitForStdOut,
				self.__vbox_manager.constants.ProcessCreateFlag_WaitForStdErr,
			]

			guest_process = process.processCreate(
				executable,
				arguments,
				"",
				environment_changes,
				flags,
				30000,
			)

			print(guest_process)

			pid = guest_process.PID
			self.__running_apps.append(VirtualMachineRunningApp(app_name=app_name, pid=pid))

			print(f"Running {app_name} on {self.name}. Guest PID: {pid}")

			process.close()
		finally:
			session.unlockMachine()

	def stop_app(self, app_name: str) -> None:
		target = None

		for app in self.__running_apps:
			if app.app_name == app_name:
				target = app
				break

		if target is None:
			return

		session = self.__vbox_manager.getSessionObject(self.__vbox)

		try:
			self.__machine.lockMachine(session, self.__vbox_manager.constants.LockType_Shared)
			console = session.console
			guest = console.guest

			guest_session = guest.createSession(
				self.__guest_username,
				self.__guest_password,
				"",
				f"{self.name}-stop-session",
			)

			guest_session.waitForArray(
				[self.__vbox_manager.constants.GuestSessionWaitForFlag_Start],
				30000,
			)

			os_type = self.__machine.OSTypeId.lower()

			if "windows" in os_type:
				executable = "C:\\Windows\\System32\\taskkill.exe"
				args = (executable, "/PID", str(target.pid), "/F")
			else:
				executable = "/bin/kill"
				args = (executable, "-9", str(target.pid))

			guest_session.processCreate(
				executable,
				args,
				tuple(),
				(self.__vbox_manager.constants.ProcessCreateFlag_WaitForProcessStartOnly),
				30000,
			)

			self.__running_apps.remove(target)
			print(f"Stopped {app_name} on {self.name}. Guest PID: {target.pid}")

			guest_session.close()

		finally:
			session.unlockMachine()

	def get_virtualbox_storage_info(self) -> VirtualMachineStorageInfo:
		total_logical_bytes = 0
		total_physical_bytes = 0
		disks: list[VirtualMachineStorageDiskInfo] = []

		for attachment in self.__machine.mediumAttachments:
			medium = attachment.medium
			if medium is None:
				continue

			if attachment.type != self.__vbox_manager.constants.DeviceType_HardDisk:
				continue

			logical_bytes = int(medium.logicalSize or 0)
			physical_bytes = int(medium.size or 0)

			total_logical_bytes += logical_bytes
			total_physical_bytes += physical_bytes

			disks.append(VirtualMachineStorageDiskInfo(
				name=medium.name,
				location=medium.location,
				format=medium.format,
				used=round(logical_bytes / (1024 ** 3), 2),
				total=round(physical_bytes / (1024 ** 3), 2),
			))

		return VirtualMachineStorageInfo(used=round(total_physical_bytes / (1024 ** 3), 2), total=round(total_logical_bytes / (1024 ** 3), 2), disks=disks)

	def calculate_utilization(self) -> VirtualMachineUtilization:
		storage_info = self.get_virtualbox_storage_info()

		return VirtualMachineUtilization(
			cpu_percent=0,
			memory_percent=self.__used_memory / self.total_memory * 100,
			storage_percent=round(storage_info.used / storage_info.total * 100)
		)

	def show_specs(self) -> None:
		storage_info = self.get_virtualbox_storage_info()

		print(
			f"VM Name: {self.name},\n"
			f"CPU: {self.total_cpu},\n"
			f"Memory: {self.available_memory / self.total_memory} MB,\n"
			f"Storage: {storage_info.used}/{storage_info.total} GB"
		)

	def __perf_monitor(self) -> None:
		while self.__perf_monitor_state:
			self.__vbox.performanceCollector.setupMetrics(
				(
					"CPU/Load/User",
					"CPU/Load/Kernel",
					"RAM/Usage",
				),
				(self.__machine,),
				1,
				5
			)

			time.sleep(5)

			(
				values,
				names,
				objects,
				units,
				scales,
				sequence_numbers,
				indices,
				lengths,
			) = self.__vbox.performanceCollector.queryMetricsData(
				(
					"CPU/Load/User",
					"CPU/Load/Kernel",
					"RAM/Usage/Used",
				),
				(self.__machine,)
			)

			values = list(values)
			names = list(names)
			units = list(units)
			scales = list(scales)
			indices = list(indices)
			lengths = list(lengths)

			used_cpu_user = 0.0
			used_cpu_kernel = 0.0
			used_memory = 0

			for i, name in enumerate(names):
				index = int(indices[i])
				length = int(lengths[i])

				raw_samples = values[index:index + length]

				if not raw_samples:
					continue

				latest_value = raw_samples[-1]

				scale = scales[i] if scales[i] else 1
				value = latest_value / scale

				unit = units[i].lower()

				if name == "CPU/Load/User":
					used_cpu_user = float(value)
				elif name == "CPU/Load/Kernel":
					used_cpu_kernel = float(value)
				elif name == "RAM/Usage/Used":
					if unit in ("kb", "kbytes", "kilobytes"):
						memory_used_mb = value / 1024
					elif unit in ("mb", "mbytes", "megabytes"):
						memory_used_mb = value
					elif unit in ("b", "bytes"):
						memory_used_mb = value / (1024 ** 2)
					else:
						memory_used_mb = value / 1024

					used_memory = int(memory_used_mb) or 0

			self.__used_cpu = used_cpu_user + used_cpu_kernel
			self.__used_memory = used_memory
