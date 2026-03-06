# Workflow: Troubleshoot Printer USB Connection

## Objective
Diagnose and resolve issues where the Python script cannot claim the USB interface of the Epson printer.

## Execution Steps
1. **Verify Physical Connection:**
   - Run `lsusb` to ensure the device `04b8:0e28` (Seiko Epson Corp.) is detected on the bus.
2. **Check Udev Rules:**
   - Verify the file `/etc/udev/rules.d/99-escpos.rules` exists and contains:
     `SUBSYSTEM=="usb", ATTR{idVendor}=="04b8", ATTR{idProduct}=="0e28", MODE="0666"`
   - If missing or incorrect, fix it and run:
     ```bash
     sudo udevadm control --reload-rules && sudo udevadm trigger
     ```
3. **Check Library Dependencies:**
   - Ensure `pyusb` is installed in the virtual environment. 
   - If `libusb` is missing at the OS level, run: `sudo apt-get install libusb-1.0-0-dev -y`.
4. **Release Kernel Driver:**
   - If the printer is claimed by the native Linux `usblp` driver, `python-escpos` cannot attach to it. 
   - Ensure the Python script handles `usb.core.USBError: [Errno 16] Resource busy` by detaching the kernel driver dynamically in the USB init phase.
