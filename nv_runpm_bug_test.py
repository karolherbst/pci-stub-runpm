#!/usr/bin/env python3
import argparse
import mmap
import os
import re
import time

parser = argparse.ArgumentParser()
parser.add_argument("-m", "--method", choices=["Q0L2", "P0L2", "P0LD", "ACPI"], help="method to use. Default: Q0L2", default="Q0L2")
parser.add_argument("-a", "--action", choices=["ON", "OFF", "cycle", "noop"], help="turns the GPU ON or OFF", default="cycle")
parser.add_argument("-g", "--gpu", help="pci address of the GPU. Default: 01:00.0", default="01:00.0")
parser.add_argument("-b", "--bus", help="pci address of the bridge controller the GPU is directly connected to. Default: 00:01.0", default="00:01.0")
parser.add_argument("--pcie-link-workaround", help="puts the pcie link to 8.0 speed", action="store_true")
parser.add_argument("--no-gpu-pci-d3hot", help="skips putting the gpu into d3hot via the pci config space", action="store_true")
args = parser.parse_args()

GPU = "0000:%s" % args.gpu
HDA = "0000:%s.%s" % (re.search('([0-9a-f]{2}:[0-9a-f]{2})', args.gpu).group(0), "1")
BUS = "0000:%s" % args.bus

MMIO_RES = 0
PCIE_PM_REG = 0x64

def scanPCI() -> None:
	f = open("/sys/bus/pci/rescan", "a")
	f.write("1")
	f.close()

def enablePCI(device: str) -> None:
	f = open("/sys/bus/pci/devices/%s/enable" % device, "a")
	f.write("1")
	f.close()

def devExists(device: str) -> bool:
	return os.path.exists("/sys/bus/pci/devices/%s/" % device)

def pcirem(device: str) -> None:
	f = open("/sys/bus/pci/devices/%s/remove" % device, "a")
	f.write("1")
	f.close()

def mmioread(offset: int) -> int:
	f = open("/sys/bus/pci/devices/%s/resource%u" % (GPU, MMIO_RES), "r+b")
	gpu_mm = mmap.mmap(f.fileno(), 0x0)
	v = int.from_bytes(gpu_mm[offset:offset+4], byteorder="little")
	gpu_mm.close()
	f.close()
	print("MMIO R 0x%06x 0x%08x" % (offset, v))
	return v

def mmiowrite(offset: int, value: int) -> None:
	print("MMIO W 0x%06x 0x%08x" % (offset, value))
	f = open("/sys/bus/pci/devices/%s/resource%u" % (GPU, MMIO_RES), "r+b")
	gpu_mm = mmap.mmap(f.fileno(), 0x0)
	gpu_mm[offset:offset+4] = value.to_bytes(4, byteorder="little")
	gpu_mm.close()
	f.close()

def mmiomask(offset: int, value: int, mask: int) -> None:
	v = mmioread(offset)
	v &= ~mask
	v |= value & mask
	mmiowrite(offset, v)

def pcipeek(device: str, offset: int) -> int:
	f = open("/sys/bus/pci/devices/%s/config" % device, "r+b")
	f.seek(offset)
	v = int.from_bytes(f.read(4), byteorder="little")
	print("PCI R %s 0x%03x 0x%08x" % (device, offset, v))
	f.close()
	return v

def pcipoke(device: str, offset: int, value: int) -> None:
	print("PCI W %s 0x%03x 0x%08x" % (device, offset, value))
	f = open("/sys/bus/pci/devices/%s/config" % device, "r+b")
	f.seek(offset)
	f.write(value.to_bytes(4, byteorder="little"))
	f.close()

def pcimask(device: str, offset: int, value: int, mask: int) -> None:
	v = pcipeek(device, offset)
	v &= ~mask
	v |= value & mask
	pcipoke(device, offset, v)

def acpi(method: str) -> None:
	# uses acpi_call kernel module
	f = open("/proc/acpi/call", "w")
	f.write(method)
	f.close()
	f = open("/proc/acpi/call", "r")
	print("ACPI %s %s " % (method, f.readline()))
	f.close()

def gpusetpcieto25():
	mmiomask(0x8c040, 0x00080000, 0x000c0000)
	mmiomask(0x8c040, 0x00000001, 0x00000001)

scanPCI()
time.sleep(0.2)

if args.action == "OFF" or args.action == "cycle":
	print("turning GPU off")

	print("set PCIe link speed to 2.5 to simulate DEVINIT")
	enablePCI(GPU)
	gpusetpcieto25()
	time.sleep(0.1)

	if args.pcie_link_workaround:
		print("set PCIe link speed to 8.0")
		mmiomask(0x8c040, 0x00000000, 0x000c0000)
		mmiomask(0x8c040, 0x00000001, 0x00000001)
		mmioread(0x8c040)
		time.sleep(0.1)

	if not args.no_gpu_pci_d3hot:
		print("put GPU into D3hot via PCI config")
		pcimask(GPU, PCIE_PM_REG, 0x3, 0x3)
		pcipeek(GPU, PCIE_PM_REG)

	print("put BUS into D3hot via PCI config")
	pcimask(BUS, 0x084, 0x3, 0x3)
	pcipeek(BUS, 0x084)

	print("disable the link on the bridge")
	if args.method == "ACPI":
		acpi("\_SB.PCI0.PEG0.PG00._OFF")
	else:
		if args.method == "Q0L2":
			# Q0L2
			pcimask(BUS, 0x248, 0x80, 0x80)
			time.sleep(0.1)
			pcipeek(BUS, 0x248)
		elif args.method == "P0L2":
			# P0L2
			pcimask(BUS, 0xbc, 0x20, 0x20)
			time.sleep(0.1)
			pcipeek(BUS, 0xbc)
		else:
			# POLD
			pcimask(BUS, 0xb0, 0x10, 0x10)
			time.sleep(0.1)
			pcipeek(BUS, 0xb0)

	pcirem(GPU)
	if devExists(HDA):
		pcirem(HDA)


if args.action == "ON" or args.action == "cycle":
	print("turning GPU on")
	print("enable the link on the bridge")

	if args.method == "ACPI":
		acpi("\_SB.PCI0.PEG0.PG00._ON")
	else:
		if args.method == "Q0L2":
			# Q0L0
			pcimask(BUS, 0x248, 0x100, 0x100)
			time.sleep(0.1)
			pcipeek(BUS, 0x248)
		elif args.method == "P0L2":
			# P0L0
			pcimask(BUS, 0xbc, 0x40, 0x40)
			time.sleep(0.1)
			pcipeek(BUS, 0xbc)
		else:
			# POLD
			pcimask(BUS, 0xb0, 0x00, 0x10)
			time.sleep(0.1)
			pcipeek(BUS, 0xb0)

	print("put BUS into D0 via PCI config")
	pcimask(BUS, 0x084, 0x0, 0x3)
	pcipeek(BUS, 0x084)

	if devExists(GPU):
		pcirem(GPU)

	if devExists(HDA):
		pcirem(HDA)

	scanPCI()
	time.sleep(0.1)
	if not devExists(GPU):
		print("GPU wasn't redetected on scan. GPU probably failed to runtime resume")
	else:
		pcipeek(GPU, PCIE_PM_REG)
