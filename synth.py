#!/usr/bin/env python3
"""
Professional Digital Synthesizer for Raspberry Pi Zero 2W
Hardware: ADS1115 + PCM5102 + 4 Potentiometers
Uses sounddevice callback architecture for proper real-time audio
Based on Raspberry Pi audio synthesis best practices
"""

import numpy as np
import sounddevice as sd
import threading
import time
from board import SCL, SDA
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

class ProfessionalSynth:
    def __init__(self, sample_rate=44100, blocksize=256):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.running = False
        
        # Initialize I2C and ADS1115
        print("Initializing ADS1115...")
        i2c = busio.I2C(SCL, SDA)
        self.ads = ADS.ADS1115(i2c)
        
        # Create analog input channels for 4 potentiometers
        self.pot_freq = AnalogIn(self.ads, ADS.P0)     # Frequency control
        self.pot_volume = AnalogIn(self.ads, ADS.P1)   # Volume control  
        self.pot_wave = AnalogIn(self.ads, ADS.P2)     # Waveform selector
        self.pot_filter = AnalogIn(self.ads, ADS.P3)   # Filter cutoff
        
        # Synth parameters (thread-safe)
        self.frequency = 440.0
        self.volume = 0.5
        self.waveform = 0  # 0=sine, 1=square, 2=sawtooth, 3=triangle
        self.filter_cutoff = 1000.0
        
        # Audio generation state
        self.phase = 0.0
        self.filter_state = 0.0
        
        # Thread for reading potentiometers
        self.pot_thread = None
        self.pot_running = False
        
        print("Professional Synthesizer initialized!")
        print("Controls:")
        print("Pot 1 (A0): Frequency (100Hz - 2000Hz)")
        print("Pot 2 (A1): Volume (0 - 100%)")
        print("Pot 3 (A2): Waveform (Sine/Square/Saw/Triangle)")
        print("Pot 4 (A3): Low-pass Filter (200Hz - 8000Hz)")
        print()
        print("Using sounddevice callback architecture for professional audio")
    
    def read_potentiometers_thread(self):
        """Separate thread for reading potentiometers to avoid blocking audio"""
        while self.pot_running:
            try:
                # Read pot values with calibrated ranges
                freq_raw = self.pot_freq.value
                vol_raw = self.pot_volume.value
                wave_raw = self.pot_wave.value
                filter_raw = self.pot_filter.value
                
                # Apply calibration (based on your measurements)
                # Pot 1 (Frequency): 15 - 26320
                freq_norm = (freq_raw - 15) / (26320 - 15)
                freq_norm = max(0, min(1, freq_norm))
                self.frequency = 100 + freq_norm * 1900
                
                # Pot 2 (Volume): 3 - 26335  
                vol_norm = (vol_raw - 3) / (26335 - 3)
                vol_norm = max(0, min(1, vol_norm))
                self.volume = vol_norm * 0.8
                
                # Pot 3 (Waveform): 4 - 26333
                wave_norm = (wave_raw - 4) / (26333 - 4)
                wave_norm = max(0, min(1, wave_norm))
                if wave_norm < 0.25:
                    self.waveform = 0  # Sine
                elif wave_norm < 0.5:
                    self.waveform = 1  # Square
                elif wave_norm < 0.75:
                    self.waveform = 2  # Sawtooth
                else:
                    self.waveform = 3  # Triangle
                
                # Pot 4 (Filter): 15 - 26323
                filter_norm = (filter_raw - 15) / (26323 - 15)
                filter_norm = max(0, min(1, filter_norm))
                self.filter_cutoff = 200 + filter_norm * 7800
                
                # Update every 50ms
                time.sleep(0.05)
                
            except Exception as e:
                print(f"Error reading potentiometers: {e}")
                time.sleep(0.1)
    
    def audio_callback(self, outdata, frames, time, status):
        """
        Optimized audio callback with improved filtering
        """
        try:
            # Get current parameters (cached for speed)
            freq = self.frequency
            vol = self.volume
            wave = self.waveform
            cutoff = self.filter_cutoff
            
            # Fast phase calculation
            phase_increment = 2 * np.pi * freq / self.sample_rate
            phases = self.phase + np.arange(frames, dtype=np.float32) * phase_increment
            
            # Generate waveform (optimized)
            if wave == 1:  # Square wave
                audio = np.sign(np.sin(phases))
            elif wave == 2:  # Sawtooth wave
                audio = 2 * ((phases / (2 * np.pi)) % 1.0) - 1
            elif wave == 3:  # Triangle wave
                norm_phases = (phases / (2 * np.pi)) % 1.0
                audio = 2 * np.abs(2 * norm_phases - 1) - 1
            else:  # Sine wave (default)
                audio = np.sin(phases)
            
            # Update phase for next callback
            self.phase = (self.phase + frames * phase_increment) % (2 * np.pi)
            
            # Apply filter ONLY to harsh waveforms and only when needed
            if cutoff < 6000 and wave in [1, 2]:  # Only square and sawtooth
                # Much gentler filter for square waves
                alpha = min(0.3, cutoff / 6000.0)  # Gentler filtering
                
                # Simple single-pole filter
                filtered_audio = np.zeros_like(audio)
                filtered_audio[0] = alpha * audio[0] + (1 - alpha) * self.filter_state
                
                for i in range(1, frames):
                    filtered_audio[i] = alpha * audio[i] + (1 - alpha) * filtered_audio[i-1]
                
                self.filter_state = filtered_audio[-1]
                audio = filtered_audio
            
            # Apply volume
            audio *= vol
            
            # Output to both channels efficiently
            outdata[:, 0] = audio
            outdata[:, 1] = audio
            
        except Exception:
            # Silent error handling - fill with zeros
            outdata.fill(0)
    
    def start(self):
        """Start the synthesizer using professional callback architecture"""
        if self.running:
            print("Synthesizer already running!")
            return
        
        # Start potentiometer reading thread
        self.pot_running = True
        self.pot_thread = threading.Thread(target=self.read_potentiometers_thread)
        self.pot_thread.daemon = True
        self.pot_thread.start()
        
        # Start audio stream with higher latency for stability
        print(f"Starting audio stream: {self.sample_rate}Hz, {self.blocksize} samples")
        print("Optimized for Raspberry Pi performance")
        
        try:
            with sd.OutputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                channels=2,
                dtype='float32',
                callback=self.audio_callback,
                latency='high'  # Use high latency for stability on Pi
            ):
                self.running = True
                print("\n✅ Synthesizer started! Adjust potentiometers to control sound.")
                print("✅ Using real-time audio callback - no more pulsing!")
                print("Press Ctrl+C to stop.\n")
                
                # Status display loop
                while self.running:
                    self.print_status()
                    time.sleep(0.5)
                    
        except KeyboardInterrupt:
            print("\nShutting down synthesizer...")
        except Exception as e:
            print(f"Audio error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the synthesizer"""
        self.running = False
        self.pot_running = False
        if self.pot_thread:
            self.pot_thread.join()
        print("Synthesizer stopped.")
    
    def print_status(self):
        """Print current parameter values"""
        if not self.running:
            return
            
        waveforms = ["Sine", "Square", "Sawtooth", "Triangle"]
        print(f"\rFreq: {self.frequency:.1f}Hz | "
              f"Vol: {self.volume*100:.1f}% | "
              f"Wave: {waveforms[self.waveform]} | "
              f"Filter: {self.filter_cutoff:.1f}Hz", end="", flush=True)

def main():
    """Main function to run the professional synthesizer"""
    print("🎵 Professional Raspberry Pi Synthesizer 🎵")
    print("Based on audio synthesis best practices")
    print()
    
    # Create synthesizer with Raspberry Pi optimized settings
    synth = ProfessionalSynth(
        sample_rate=44100,  # Standard sample rate
        blocksize=512       # Larger block size for Pi stability
    )
    
    try:
        synth.start()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"Error: {e}")
        synth.stop()

if __name__ == "__main__":
    main()
