#!/usr/bin/env python3
"""
MIDI Keyboard Test Script for Raspberry Pi Zero 2W
Tests MIDI input and shows note data
Run this first to verify your MIDI keyboard is working
"""

import time
import rtmidi
import threading

class MIDITester:
    def __init__(self):
        self.midiin = None
        self.running = False
        self.notes_pressed = set()
        
    def list_midi_devices(self):
        """List all available MIDI input devices"""
        print("🎹 Scanning for MIDI devices...")
        print("=" * 50)
        
        try:
            temp_midi = rtmidi.MidiIn()
            ports = temp_midi.get_ports()
            
            if not ports:
                print("❌ No MIDI devices found!")
                print("\nTroubleshooting:")
                print("1. Make sure your MIDI keyboard is connected via USB")
                print("2. Check that your Pi is in USB host mode")
                print("3. Try: lsusb to see if device is detected")
                print("4. Some keyboards need to be powered on first")
                return None
            
            print(f"✅ Found {len(ports)} MIDI device(s):")
            for i, port in enumerate(ports):
                print(f"  {i}: {port}")
            
            temp_midi.close_port()
            del temp_midi
            return ports
            
        except Exception as e:
            print(f"❌ Error scanning MIDI devices: {e}")
            return None
    
    def note_number_to_name(self, note_number):
        """Convert MIDI note number to note name"""
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (note_number // 12) - 1
        note = notes[note_number % 12]
        return f"{note}{octave}"
    
    def note_to_frequency(self, note_number):
        """Convert MIDI note number to frequency in Hz"""
        return 440.0 * (2 ** ((note_number - 69) / 12.0))
    
    def midi_callback(self, message, data):
        """Handle incoming MIDI messages"""
        try:
            msg, deltatime = message
            
            if len(msg) >= 3:
                status = msg[0]
                note = msg[1]
                velocity = msg[2]
                
                # Note On (status 144-159) with velocity > 0
                if 144 <= status <= 159 and velocity > 0:
                    self.notes_pressed.add(note)
                    note_name = self.note_number_to_name(note)
                    frequency = self.note_to_frequency(note)
                    channel = (status & 0x0F) + 1
                    
                    print(f"🎵 NOTE ON:  {note_name} (#{note}) | "
                          f"Vel: {velocity:3d} | Freq: {frequency:6.1f}Hz | Ch: {channel}")
                
                # Note Off (status 128-143) or Note On with velocity 0
                elif (128 <= status <= 143) or (144 <= status <= 159 and velocity == 0):
                    if note in self.notes_pressed:
                        self.notes_pressed.remove(note)
                    note_name = self.note_number_to_name(note)
                    channel = (status & 0x0F) + 1
                    
                    print(f"🔇 NOTE OFF: {note_name} (#{note}) | Ch: {channel}")
                
                # Control Change (status 176-191)
                elif 176 <= status <= 191:
                    controller = note  # In CC messages, second byte is controller
                    value = velocity   # In CC messages, third byte is value
                    channel = (status & 0x0F) + 1
                    
                    print(f"🎛️  CC: Controller {controller:3d} = {value:3d} | Ch: {channel}")
                
                # Pitch Bend (status 224-239)
                elif 224 <= status <= 239:
                    # Pitch bend uses both data bytes
                    pitch_value = note + (velocity << 7) - 8192
                    channel = (status & 0x0F) + 1
                    
                    print(f"🎪 PITCH: {pitch_value:5d} | Ch: {channel}")
                
                # Program Change (status 192-207)
                elif 192 <= status <= 207:
                    program = note
                    channel = (status & 0x0F) + 1
                    
                    print(f"🎸 PROGRAM: {program:3d} | Ch: {channel}")
        
        except Exception as e:
            print(f"❌ Error processing MIDI: {e}")
    
    def status_display(self):
        """Display current status"""
        while self.running:
            if self.notes_pressed:
                note_names = [self.note_number_to_name(note) for note in sorted(self.notes_pressed)]
                print(f"\r🎹 Playing: {', '.join(note_names)}", end="", flush=True)
            time.sleep(0.1)
    
    def connect_midi_device(self, device_index=0):
        """Connect to a MIDI device"""
        try:
            self.midiin = rtmidi.MidiIn()
            ports = self.midiin.get_ports()
            
            if device_index >= len(ports):
                print(f"❌ Device index {device_index} not available")
                return False
            
            port_name = ports[device_index]
            self.midiin.open_port(device_index)
            self.midiin.set_callback(self.midi_callback)
            
            print(f"✅ Connected to: {port_name}")
            print(f"✅ Listening for MIDI data...")
            print("\nMIDI Activity:")
            print("-" * 80)
            
            return True
            
        except Exception as e:
            print(f"❌ Error connecting to MIDI device: {e}")
            return False
    
    def start_monitoring(self, device_index=0):
        """Start monitoring MIDI input"""
        if not self.connect_midi_device(device_index):
            return
        
        self.running = True
        
        # Start status display thread
        status_thread = threading.Thread(target=self.status_display)
        status_thread.daemon = True
        status_thread.start()
        
        try:
            print("\n🎹 MIDI Monitor Active!")
            print("Play your keyboard to see MIDI data")
            print("Press Ctrl+C to stop")
            print("=" * 80)
            
            while self.running:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping MIDI monitor...")
        
        finally:
            self.stop()
    
    def stop(self):
        """Stop MIDI monitoring"""
        self.running = False
        if self.midiin:
            self.midiin.close_port()
            del self.midiin
        print("✅ MIDI monitor stopped")

def main():
    """Main function"""
    print("🎹 MIDI Keyboard Test Script")
    print("=" * 40)
    
    tester = MIDITester()
    
    # List available devices
    ports = tester.list_midi_devices()
    if not ports:
        return
    
    print("\n" + "=" * 50)
    
    # Auto-connect to first device or let user choose
    if len(ports) == 1:
        print(f"Auto-connecting to: {ports[0]}")
        device_index = 0
    else:
        try:
            device_index = int(input(f"\nSelect device (0-{len(ports)-1}): "))
            if device_index < 0 or device_index >= len(ports):
                print("Invalid selection, using device 0")
                device_index = 0
        except ValueError:
            print("Invalid input, using device 0")
            device_index = 0
    
    # Start monitoring
    tester.start_monitoring(device_index)

if __name__ == "__main__":
    main()

