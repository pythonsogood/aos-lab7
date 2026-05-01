import math
import time
from contextlib import suppress
from threading import Thread
from typing import Any, Iterable, Literal, NamedTuple

import pywintypes
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


class VirtualMachine:
	def __init__(self, id: int, machine: Any, manager: vboxapi.VirtualBoxManager, username: str, password: str) -> None:
		self.__id = id
		self.__machine = machine

		self.__vbox_manager = manager
		self.__vbox = manager.getVirtualBox()

		self.__guest_username = username
		self.__guest_password = password

		self.__running_apps = []

		self.__used_cpu = 0
		self.__used_memory = 0

		self.__guest_session: Any | None = None
		self.__control_session: Any | None = None

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
		return self.__machine.OSTypeId

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
	def running_apps(self) -> tuple[Any, ...]:
		return tuple(self.__running_apps)

	def start_vm(self, frontend: VirtualBoxFrontend = "headless") -> None:
		session = self.__vbox_manager.getSessionObject(self.__vbox)
		progress = self.__machine.launchVMProcess(session, frontend, ())
		progress.waitForCompletion(-1)

		print(f"Started VM {self.name}")

		session.unlockMachine()

		self.__perf_monitor_state = True

		if self.__perf_monitor_thread is None:
			self.__perf_monitor_thread = Thread(target=self.__perf_monitor, daemon=True)
			self.__perf_monitor_thread.start()

	def stop_vm(self) -> None:
		self.__perf_monitor_state = False

		if (perf_thread := self.__perf_monitor_thread) is not None:
			perf_thread.join()
			self.__perf_monitor_thread = None

		self._close_guest_session()

		session = self.__vbox_manager.getSessionObject(self.__vbox)
		self.__machine.lockMachine(session, self.__vbox_manager.constants.LockType_Shared)

		try:
			progress = session.console.powerDown()
			progress.waitForCompletion(-1)
			print(f"Stopped VM {self.name}")
		finally:
			session.unlockMachine()

	def run_app(self, executable: str, args: Iterable[str] | None = None) -> int:
		if args is None:
			args = ()

		self._create_guest_session()

		if self.__guest_session is None:
			raise ValueError("Guest session is not created")

		environment_changes = ()

		guest_process = self.__guest_session.processCreate(executable, (executable, *args), "", environment_changes, (
			self.__vbox_manager.constants.ProcessCreateFlag_WaitForProcessStartOnly,
		), 0)

		guest_process.waitForArray((self.__vbox_manager.constants.ProcessWaitForFlag_Start,), 30000)

		self.__running_apps.append(guest_process)

		print(f"Running {guest_process.Name if guest_process.Name.strip() else f'{executable} with PID {guest_process.PID}'} on {self.name}.")

		return guest_process.PID

	def stop_app(self, process_id: int) -> None:
		for i, app in enumerate(self.__running_apps):
			if app.PID == process_id:
				app_name = app.Name

				try:
					app.terminate()

					app.waitForArray((self.__vbox_manager.constants.ProcessWaitForFlag_Terminate,), 3000)
				except Exception:
					self._kill_pid(process_id)

				print(f"Stopped app {app_name if app_name.strip() else f'with PID {process_id}'} on {self.name}.")

				self.__running_apps.pop(i)
				break
		else:
			self._kill_pid(process_id)

			print(f"Stopped app with PID {process_id} on {self.name}.")

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
				used=round(physical_bytes / (1024 ** 3), 2),
				total=round(logical_bytes / (1024 ** 3), 2),
			))

		return VirtualMachineStorageInfo(used=round(total_physical_bytes / (1024 ** 3), 2), total=round(total_logical_bytes / (1024 ** 3), 2), disks=disks)

	def calculate_utilization(self) -> VirtualMachineUtilization:
		storage_info = self.get_virtualbox_storage_info()

		return VirtualMachineUtilization(
			cpu_percent=self.__used_cpu,
			memory_percent=self.__used_memory / self.total_memory * 100 if self.total_memory > 0 else 0,
			storage_percent=round(storage_info.used / storage_info.total * 100) if storage_info.total > 0 else 0
		)

	def show_specs(self) -> None:
		storage_info = self.get_virtualbox_storage_info()

		print(f"VM Name: {self.name}, CPU: {self.total_cpu}, Memory: {self.available_memory}/{self.total_memory}, Storage: {storage_info.used}/{storage_info.total}")

	def _kill_pid(self, process_id: int) -> None:
		self._create_guest_session()

		if self.__guest_session is None:
			raise ValueError("Guest session is not created")

		executable = "/bin/kill"
		args = (executable, "-9", str(process_id))
		environment_changes = ()

		os_type = self.__machine.OSTypeId.lower()

		if "windows" in os_type:
			executable = r"C:\Windows\System32\taskkill.exe"
			args = (executable, "/PID", str(process_id), "/F")

		kill_process = self.__guest_session.processCreate(
			executable,
			args,
			environment_changes,
			(self.__vbox_manager.constants.ProcessCreateFlag_WaitForProcessStartOnly,),
			30000,
		)

		kill_process.waitForArray((self.__vbox_manager.constants.ProcessWaitForFlag_Terminate,), 3000)

	def _create_guest_session(self) -> None:
		if self.__guest_session is not None:
			return

		last_error: Exception | None = None

		for attempt in range(1, 11):
			session = self.__vbox_manager.getSessionObject(self.__vbox)

			try:
				self.__machine.lockMachine(session, self.__vbox_manager.constants.LockType_Shared)
				guest_session = session.console.guest.createSession(
					self.__guest_username,
					self.__guest_password,
					"",
					f"{self.name}-guest-session",
				)
				guest_session.waitForArray((self.__vbox_manager.constants.GuestSessionWaitForFlag_Start,), 5000)
			except pywintypes.com_error as error:
				last_error = error
				with suppress(Exception):
					session.unlockMachine()

				if attempt < 10:
					print(f"Guest execution service not ready on {self.name} (attempt {attempt}/10); retrying...")
					time.sleep(5)
					continue

				raise
			except Exception as error:
				last_error = error
				with suppress(Exception):
					session.unlockMachine()
				raise
			else:
				self.__control_session = session
				self.__guest_session = guest_session
				return

		if last_error is not None:
			raise last_error

		raise RuntimeError(f"Failed to create guest session on {self.name}")

	def _close_guest_session(self) -> None:
		if self.__guest_session is not None:
			with suppress(Exception):
				self.__guest_session.close()

			self.__guest_session = None

		if self.__control_session is not None:
			with suppress(Exception):
				self.__control_session.unlockMachine()

			self.__control_session = None

	def __perf_monitor(self) -> None:
		while self.__perf_monitor_state:
			try:
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
			except Exception:
				pass
			except KeyboardInterrupt:
				self.__perf_monitor_state = False
				break

		self.__used_cpu = 0
		self.__used_memory = 0
