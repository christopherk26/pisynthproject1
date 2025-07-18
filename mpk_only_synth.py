#!/usr/bin/env python3
"""
MPK mini 3 Only Synthesizer
Uses ONLY the MPK mini 3 - no external potentiometers needed!
8 knobs + keys + pads for complete control
"""

import numpy as np
import sounddevice as sd
import threading
import time
import rtmidi

class MPKVoice:
    """Voice for MPK-controlled synthesis"""
    def __init__(self, note, velocity, sample_rate, synth_params):
        self.note = note
        self.velocity = velocity / 127.0
        self.frequency = 440.0 * (2 ** ((note - 69) / 12.0))
        self.phase = 0.0
        self.sample_rate = sample_rate
        
        # Copy envelope parameters from synth
        self.attack_time = synth_params['attack']
        self.decay_time = synth_params['decay']
        self.sustain_level = synth_params['sustain']
        self.release_time = synth_params['release']
        
        # Envelope state
        self.envelope_phase = 'attack'
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
        if waveform == 1:  # Square
            audio = np.sign(np.sin(phases))
        elif waveform == 2:  # Sawtooth
            audio = 2 * ((phases / (2 * np.pi)) % 1.0) - 1
        elif waveform == 3:  # Triangle
            norm_phases = (phases / (2 * np.pi)) % 1.0
            audio = 2 * np.abs(2 * norm_phases - 1) - 1
        else:  # Sine
            audio = np.sin(phases)
        
        # Update phase
        self.phase = (self.phase + frames * phase_increment) % (2 * np.pi)
        
        # Apply filter
        if filter_cutoff < 6000 and waveform in [1, 2]:
            alpha = min(0.5, filter_cutoff / 6000.0)
            for i in range(frames):
                self.filter_state = alpha * audio[i] + (1 - alpha) * self.filter_state
                audio[i] = self.filter_state
        
        # Apply envelope
        envelope = self.update_envelope(frames)
        audio *= envelope * self.velocity
        
        return audio

class MPKOnlySynth:
    def __init__(self, sample_rate=44100, blocksize=512):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.running = False
        
        # Synth parameters controlled by MPK knobs
        self.master_volume = 0.5      # Knob 1 (CC 70)
        self.waveform = 0             # Knob 2 (CC 71) 
        self.filter_cutoff = 1000.0   # Knob 3 (CC 72)
        self.attack_time = 0.01       # Knob 4 (CC 73)
        self.decay_time = 0.1         # Knob 5 (CC 74)
        self.sustain_level = 0.7      # Knob 6 (CC 75)
        self.release_time = 0.3       # Knob 7 (CC 76)
        self.detune = 0.0             # Knob 8 (CC 77)
        
        # MIDI and voice management
        self.voices = {}
        self.midiin = None
        self.max_voices = 16  # More polyphony since no pot reading!
        
        print("🎹 MPK mini 3 ONLY Synthesizer")
        print("=" * 40)
        print("No external hardware needed!")
        print("Control everything with your MPK mini 3:")
        print()
        print("🎹 KEYS: Play notes")
        print("🥁 PADS: Trigger notes/samples")
        print("🎛️  KNOBS:")
        print("   Knob 1: Master Volume")
        print("   Knob 2: Waveform (Sine→Square→Saw→Triangle)")
        print("   Knob 3: Filter Cutoff")
        print("   Knob 4: Attack Time")
        print("   Knob 5: Decay Time") 
        print("   Knob 6: Sustain Level")
        print("   Knob 7: Release Time")
        print("   Knob 8: Detune/Pitch Bend")
    
    def setup_midi(self):
        """Setup MIDI input"""
        try:
            self.midiin = rtmidi.MidiIn()
            ports = self.midiin.get_ports()
            
            # Look for MPK mini 3
            mpk_port = None
            for i, port in enumerate(ports):
                if "MPK mini 3" in port:
                    mpk_port = i
                    break
            
            if mpk_port is None:
                print("❌ MPK mini 3 not found!")
                print("Available ports:", ports)
                return False
            
            self.midiin.open_port(mpk_port)
            self.midiin.set_callback(self.midi_callback)
            print(f"✅ Connected to: {ports[mpk_port]}")
            return True
            
        except Exception as e:
            print(f"❌ MIDI setup failed: {e}")
            return False
    
    def midi_callback(self, message, data):
        """Handle all MIDI messages from MPK mini 3"""
        try:
            msg, deltatime = message
            
            if len(msg) >= 3:
                status = msg[0]
                data1 = msg[1]
                data2 = msg[2]
                
                # Note On (keys and pads)
                if 144 <= status <= 159 and data2 > 0:
                    self.note_on(data1, data2)
                
                # Note Off
                elif (128 <= status <= 143) or (144 <= status <= 159 and data2 == 0):
                    self.note_off(data1)
                
                # Control Change (knobs)
                elif 176 <= status <= 191:
                    self.handle_knob(data1, data2)
        
        except Exception as e:
            print(f"MIDI error: {e}")
    
    def handle_knob(self, controller, value):
        """Handle MPK mini 3 knob movements"""
        # Normalize value to 0-1
        norm_value = value / 127.0
        
        if controller == 70:    # Knob 1 - Master Volume
            self.master_volume = norm_value * 0.8
            
        elif controller == 71:  # Knob 2 - Waveform
            if norm_value < 0.25:
                self.waveform = 0  # Sine
            elif norm_value < 0.5:
                self.waveform = 1  # Square
            elif norm_value < 0.75:
                self.waveform = 2  # Sawtooth
            else:
                self.waveform = 3  # Triangle
                
        elif controller == 72:  # Knob 3 - Filter
            self.filter_cutoff = 200 + norm_value * 7800
            
        elif controller == 73:  # Knob 4 - Attack
            self.attack_time = 0.001 + norm_value * 2.0  # 1ms to 2s
            
        elif controller == 74:  # Knob 5 - Decay
            self.decay_time = 0.01 + norm_value * 2.0   # 10ms to 2s
            
        elif controller == 75:  # Knob 6 - Sustain
            self.sustain_level = norm_value
            
        elif controller == 76:  # Knob 7 - Release
            self.release_time = 0.01 + norm_value * 4.0  # 10ms to 4s
            
        elif controller == 77:  # Knob 8 - Detune
            self.detune = (norm_value - 0.5) * 200  # ±100 cents
    
    def get_synth_params(self):
        """Get current synth parameters for new voices"""
        return {
            'attack': self.attack_time,
            'decay': self.decay_time,
            'sustain': self.sustain_level,
            'release': self.release_time
        }
    
    def note_on(self, note, velocity):
        """Start playing a note"""
        # Get current synth settings for this voice
        synth_params = self.get_synth_params()
        
        # Remove old voice if note is already playing
        if note in self.voices:
            del self.voices[note]
        
        # Limit polyphony
        if len(self.voices) >= self.max_voices:
            oldest_note = min(self.voices.keys())
            del self.voices[oldest_note]
        
        # Create new voice
        self.voices[note] = MPKVoice(note, velocity, self.sample_rate, synth_params)
    
    def note_off(self, note):
        """Stop playing a note"""
        if note in self.voices:
            self.voices[note].release()
    
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
            
            # Soft limiting
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
            return
        
        # Start audio
        print(f"\nStarting audio: {self.sample_rate}Hz, {self.blocksize} samples")
        
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
                print("\n🎹 MPK mini 3 Synthesizer Ready!")
                print("🎵 Play keys and turn knobs to control sound")
                print("🥁 Use pads for percussion sounds")
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
        
        print(f"\rVoices: {active_notes:2d}/16 | "
              f"Vol: {self.master_volume*100:.0f}% | "
              f"Wave: {waveforms[self.waveform]} | "
              f"Filter: {self.filter_cutoff:.0f}Hz | "
              f"ADSR: {self.attack_time:.2f}/{self.decay_time:.2f}/{self.sustain_level:.2f}/{self.release_time:.2f} | "
              f"Detune: {self.detune:+.0f}¢", end="", flush=True)

def main():
    """Main function"""
    print("🎹 MPK mini 3 ONLY Digital Synthesizer")
    print("Complete control with just your MPK mini 3!")
    print("No external potentiometers or hardware needed")
    print("=" * 50)
    
    synth = MPKOnlySynth(
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
