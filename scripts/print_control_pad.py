from escpos.printer import Usb

try:
    p = Usb(0x04b8, 0x0e28)
    p.hw("INIT")
    p.set(align='center', font='a', width=2, height=2, bold=True)
    p.text("🧠🧠 DOPAMINE CONTROL PAD\n\n")
    
    # 1. PLAY BUTTON
    p.set(align='center', width=1, height=1)
    p.text("--- START / RESUME ---\n")
    p.barcode("CMD:PLAY", "CODE128", height=80, width=3, pos="BELOW")
    p.text("\n\n")
    
    # 2. PAUSE BUTTON
    p.text("--- PAUSE / BREAK ---\n")
    p.barcode("CMD:PAUS", "CODE128", height=80, width=3, pos="BELOW")
    p.text("\n\n")
    
    # 3. DONE BUTTON
    p.text("--- COMPLETE TASK ---\n")
    p.barcode("CMD:DONE", "CODE128", height=80, width=3, pos="BELOW")
    p.text("\n\n\n\n")
    
    p.cut()
    p.close()
    print("✅ 1D Control Pad Printed!")
except Exception as e:
    print(f"Failed to print: {e}")
