#!/usr/bin/env python3
"""
5-Potentiometer MIDI Polyphonic Synthesizer
Hardware: ADS1115 + PCM5102 + 5 Potentiometers + MPK mini 3
Advanced polyphonic synthesizer with full envelope control
"""

import numpy as np
import sounddevice as sd
import threading
import time
import rtmidi
from board import SCL, SDA
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

class PolyphonicVoice:
    """Advanced voice with full ADSR envelope"""
    def __init__(self, note, velocity, sample_rate, envelope_params):
        self.note = note
        self.velocity = velocity / 127.0
        self.frequency = 440.0 * (2 ** ((note - 69) / 12.0))
        self.phase = 0.0
        self.sample_rate = sample_rate
        
        # ADSR Envelope
        self.attack_time = envelope_params['attack']
        self.decay_time = envelope_params['decay'] 
        self.sustain_level = envelope_params['sustain']
        self.release_time = envelope_params['release']
        
        # Envelope state
        self.envelope_phase = 'attack'  # attack, decay, sustain, release, finished
        self.envelope_value = 0.0
        self.envelope_timer = 0.0
        self.releasing = False
        
        # Filter state
        self.filter_state = 0.0
    
    def release(self):
        """Start note release"""
        self.releasing = True
        self.envelope_phase = 'release'
        self.envelope_timer = 0.0
    
    def is_finished(self):
        """Check if voice is finished"""
        return self.envelope_phase == 'finished'
    
    def update_envelope(self, frames):
        """Update ADSR envelope"""
        dt = frames / self.sample_rate
        self.envelope_timer += dt
        
        if self.envelope_phase == 'attack':
            if self.attack_time > 0:
                progress = min(1.0, self.envelope_timer / self.attack_time)
                self.envelope_value = progress
                if progress >= 1.0:
                    self.envelope_phase = 'decay'
                    self.envelope_timer = 0.0
            else:
                self.envelope_value = 1.0
                self.envelope_phase = 'decay'
                
        elif self.envelope_phase == 'decay':
            if self.decay_time > 0:
                progress = min(1.0, self.envelope_timer / self.decay_time)
                self.envelope_value = 1.0 - progress * (1.0 - self.sustain_level)
                if progress >= 1.0:
                    self.envelope_phase = 'sustain'
            else:
                self.envelope_value = self.sustain_level
                self.envelope_phase = 'sustain'
                
        elif self.envelope_phase == 'sustain':
            self.envelope_value = self.sustain_level
            
        elif self.envelope_phase == 'release':
            if self.release_time > 0:
                progress = min(1.0, self.envelope_timer / self.release_time)
                self.envelope_value = self.sustain_level * (1.0 - progress)
                if progress >= 1.0:
                    self.envelope_phase = 'finished'
            else:
                self.envelope_phase = 'finished'
        
        return self.envelope_value
    
    def generate(self, frames, waveform, filter_cutoff, detune):
        """Generate audio for this voice"""
        if self.envelope_phase == 'finished':
            return np.zeros(frames, dtype=np.float32)
        
        # Apply detune
        detuned_freq = self.frequency * (2 ** (detune / 1200.0))
        
        # Generate phase array
        phase_increment = 2 * np.pi * detuned_freq / self.sample_rate
        phases = self.phase + np.arange(frames, dtype=np.float32) * phase_increment
        
        # Generate waveform
        if waveform == 1:  # Square wave
            audio = np.sign(np.sin(phases))
        elif waveform == 2:  # Sawtooth wave
            audio = 2 * ((phases / (2 * np.pi)) % 1.0) - 1
        elif waveform == 3:  # Triangle wave
            norm_phases = (phases / (2 * np.pi)) % 1.0
            audio = 2 * np.abs(2 * norm_phases - 1) - 1
        else:  # Sine wave
            audio = np.sin(phases)
        
        # Update phase
        self.phase = (self.phase + frames * phase_increment) % (2 * np.pi)
        
        # Apply filter if needed
        if filter_cutoff < 6000 and waveform in [1, 2]:
            alpha = min(0.5, filter_cutoff / 6000.0)
            for i in range(frames):
                self.filter_state = alpha * audio[i] + (1 - alpha) * self.filter_state
                audio[i] = self.filter_state
        
        # Apply envelope
        envelope = self.update_envelope(frames)
        audio *= envelope * self.velocity
        
        return audio

class FourPotMIDISynth:
    def __init__(self, sample_rate=44100, blocksize=512):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.running = False
        
        # Initialize I2C and ADS1115
        print("Initializing ADS1115 for 4-pot control...")
        i2c = busio.I2C(SCL, SDA)
        self.ads = ADS.ADS1115(i2c)
        
        # Create analog input channels for 4 potentiometers
        self.pot_volume = AnalogIn(self.ads, ADS.P0)   # Master volume
        self.pot_wave = AnalogIn(self.ads, ADS.P1)     # Waveform
        self.pot_filter = AnalogIn(self.ads, ADS.P2)   # Filter cutoff
        self.pot_envelope = AnalogIn(self.ads, ADS.P3) # Envelope control
        
        # Synth parameters
        self.master_volume = 0.5
        self.waveform = 0
        self.filter_cutoff = 1000.0
        self.envelope_control = 0.5  # Controls overall envelope timing
        self.detune = 0.0           # Controlled by MPK knobs
        
        # MIDI and voice management
        self.voices = {}
        self.midiin = None
        self.max_voices = 12  # More polyphony!
        
        # Threading
        self.pot_thread = None
        self.pot_running = False
        
        print("🎹 4-Pot MIDI Polyphonic Synthesizer")
        print("Controls:")
        print("Pot 1 (A0): Master Volume (0 - 100%)")
        print("Pot 2 (A1): Waveform (Sine/Square/Saw/Triangle)")
        print("Pot 3 (A2): Filter Cutoff (200Hz - 8000Hz)")
        print("Pot 4 (A3): Envelope Speed (Fast - Slow)")
        print("MPK Knobs: Pitch bend and effects")
    
    def get_envelope_params(self):
        """Get current envelope parameters based on pot position"""
        # Base envelope times (in seconds)
        base_attack = 0.01
        base_decay = 0.1
        base_sustain = 0.7
        base_release = 0.3
        
        # Scale envelope times based on envelope control pot
        scale = 0.1 + (self.envelope_control * 4.0)  # 0.1x to 4.1x speed
        
        return {
            'attack': base_attack * scale,
            'decay': base_decay * scale,
            'sustain': base_sustain,
            'release': base_release * scale
        }
    
    def setup_midi(self):
        """Setup MIDI input"""
        try:
            self.midiin = rtmidi.MidiIn()
            ports = self.midiin.get_ports()
            
            # Look for MPK mini 3 specifically
            mpk_port = None
            for i, port in enumerate(ports):
                if "MPK mini 3" in port:
                    mpk_port = i
                    break
            
            if mpk_port is None:
                print("⚠️  MPK mini 3 not found")
                return False
            
            self.midiin.open_port(mpk_port)
            self.midiin.set_callback(self.midi_callback)
            print(f"✅ Connected to: {ports[mpk_port]}")
            return True
            
        except Exception as e:
            print(f"❌ MIDI setup failed: {e}")
            return False
    
    def midi_callback(self, message, data):
        """Handle incoming MIDI messages"""
        try:
            msg, deltatime = message
            
            if len(msg) >= 3:
                status = msg[0]
                note = msg[1]
                velocity = msg[2]
                
                # Note On
                if 144 <= status <= 159 and velocity > 0:
                    self.note_on(note, velocity)
                
                # Note Off
                elif (128 <= status <= 143) or (144 <= status <= 159 and velocity == 0):
                    self.note_off(note)
                
                # Control Change (knobs on MPK mini 3)
                elif 176 <= status <= 191:
                    controller = note
                    value = velocity
                    self.handle_cc(controller, value)
        
        except Exception as e:
            print(f"MIDI error: {e}")
    
    def handle_cc(self, controller, value):
        """Handle MIDI control change messages from MPK mini 3 knobs"""
        # Map MPK mini 3 knobs to additional parameters
        if controller == 70:  # Knob 1
            self.detune = (value - 64) * 2  # ±128 cents
        elif controller == 71:  # Knob 2  
            # Could control something else like chorus, delay, etc.
            pass
    
    def note_on(self, note, velocity):
        """Start playing a note"""
        # Get current envelope settings
        envelope_params = self.get_envelope_params()
        
        # Remove old voice if note is already playing
        if note in self.voices:
            del self.voices[note]
        
        # Limit polyphony
        if len(self.voices) >= self.max_voices:
            # Remove oldest voice
            oldest_note = min(self.voices.keys())
            del self.voices[oldest_note]
        
        # Create new voice with current envelope settings
        self.voices[note] = PolyphonicVoice(note, velocity, self.sample_rate, envelope_params)
    
    def note_off(self, note):
        """Stop playing a note"""
        if note in self.voices:
            self.voices[note].release()
    
    def read_potentiometers_thread(self):
        """Read potentiometers in separate thread"""
        while self.pot_running:
            try:
                # Read pot values
                vol_raw = self.pot_volume.value
                wave_raw = self.pot_wave.value
                filter_raw = self.pot_filter.value
                env_raw = self.pot_envelope.value
                
                # Apply calibration (using your measured ranges)
                # Pot 1 (Volume): 3 - 26335  
                vol_norm = (vol_raw - 3) / (26335 - 3)
                vol_norm = max(0, min(1, vol_norm))
                self.master_volume = vol_norm * 0.8
                
                # Pot 2 (Waveform): 4 - 26333
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
                
                # Pot 3 (Filter): 15 - 26323
                filter_norm = (filter_raw - 15) / (26323 - 15)
                filter_norm = max(0, min(1, filter_norm))
                self.filter_cutoff = 200 + filter_norm * 7800
                
                # Pot 4 (Envelope): Same range as others
                env_norm = (env_raw - 15) / (26320 - 15)
                env_norm = max(0, min(1, env_norm))
                self.envelope_control = env_norm
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"Pot read error: {e}")
                time.sleep(0.1)
    
    def audio_callback(self, outdata, frames, time, status):
        """Generate polyphonic audio"""
        try:
            # Initialize output
            audio = np.zeros(frames, dtype=np.float32)
            
            # Mix all active voices
            voices_to_remove = []
            for note, voice in self.voices.items():
                if voice.is_finished():
                    voices_to_remove.append(note)
                else:
                    voice_audio = voice.generate(frames, self.waveform, 
                                               self.filter_cutoff, self.detune)
                    audio += voice_audio
            
            # Remove finished voices
            for note in voices_to_remove:
                del self.voices[note]
            
            # Apply master volume
            audio *= self.master_volume
            
            # Soft limiting to prevent harsh clipping
            audio = np.tanh(audio * 0.7) * 1.2
            
            # Output to both channels
            outdata[:, 0] = audio
            outdata[:, 1] = audio
            
        except Exception:
            outdata.fill(0)
    
    def start(self):
        """Start the synthesizer"""
        if self.running:
            return
        
        # Setup MIDI
        if not self.setup_midi():
            print("❌ Cannot continue without MPK mini 3")
            return
        
        # Start potentiometer thread
        self.pot_running = True
        self.pot_thread = threading.Thread(target=self.read_potentiometers_thread)
        self.pot_thread.daemon = True
        self.pot_thread.start()
        
        # Start audio
        print(f"Starting audio: {self.sample_rate}Hz, {self.blocksize} samples")
        
        try:
            with sd.OutputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                channels=2,
                dtype='float32',
                callback=self.audio_callback,
                latency='high'
            ):
                self.running = True
                print("\n🎹 MIDI Polyphonic Synthesizer Ready!")
                print("🎵 Play chords on your MPK mini 3!")
                print("🎛️  Use pots to control sound in real-time")
                print("🎚️  Use MPK knobs for pitch bend and effects")
                print("\nPress Ctrl+C to stop")
                print("=" * 60)
                
                while self.running:
                    self.print_status()
                    time.sleep(0.5)
                    
        except KeyboardInterrupt:
            print("\nShutting down...")
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
        
        if self.midiin:
            self.midiin.close_port()
            del self.midiin
        
        print("Synthesizer stopped")
    
    def print_status(self):
        """Print current status"""
        if not self.running:
            return
        
        waveforms = ["Sine", "Square", "Sawtooth", "Triangle"]
        active_notes = len(self.voices)
        envelope_speed = "Fast" if self.envelope_control < 0.3 else "Med" if self.envelope_control < 0.7 else "Slow"
        
        print(f"\rVoices: {active_notes:2d}/12 | "
              f"Vol: {self.master_volume*100:.0f}% | "
              f"Wave: {waveforms[self.waveform]} | "
              f"Filter: {self.filter_cutoff:.0f}Hz | "
              f"Env: {envelope_speed} | "
              f"Detune: {self.detune:+.0f}¢", end="", flush=True)

def main():
    """Main function"""
    print("🎹 4-Potentiometer MIDI Polyphonic Synthesizer")
    print("Designed for MPK mini 3 + 4 Potentiometers")
    print("Advanced ADSR envelope control")
    print("=" * 50)
    
    synth = FourPotMIDISynth(
        sample_rate=44100,
        blocksize=512
    )
    
    try:
        synth.start()
    except KeyboardInterrupt:
        print("Goodbye!")
    except Exception as e:
        print(f"Error: {e}")
        synth.stop()

if __name__ == "__main__":
    main()
