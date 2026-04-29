from hypervisor import Hypervisor


def main() -> None:
	hv = Hypervisor(1, "Hypervisor1")

	vm1 = hv.create_vm(1, "maku10mini", "user", "1")

	print(vm1.run_app("notepad", r"C:\Windows\System32\calc.exe"))


if __name__ == "__main__":
    main()
