#!/usr/bin/env python3
"""
Potentiometer Calibration Tool for Digital Synthesizer
Use this to find the actual min/max values of your pots
Run this first, then update your synth code with the results
"""

import time
import json
from board import SCL, SDA
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

class PotCalibrator:
    def __init__(self):
        # Initialize I2C and ADS1115
        print("Initializing ADS1115 for calibration...")
        i2c = busio.I2C(SCL, SDA)
        self.ads = ADS.ADS1115(i2c)
        
        # Create analog input channels
        self.pot0 = AnalogIn(self.ads, ADS.P0)  # Frequency
        self.pot1 = AnalogIn(self.ads, ADS.P1)  # Volume  
        self.pot2 = AnalogIn(self.ads, ADS.P2)  # Waveform
        self.pot3 = AnalogIn(self.ads, ADS.P3)  # Filter
        
        # Track min/max values
        self.min_vals = [65535, 65535, 65535, 65535]
        self.max_vals = [0, 0, 0, 0]
        
        # Pot names for display
        self.pot_names = ["Frequency", "Volume", "Waveform", "Filter"]
    
    def read_pots(self):
        """Read all potentiometer values"""
        return [
            self.pot0.value,
            self.pot1.value, 
            self.pot2.value,
            self.pot3.value
        ]
    
    def update_ranges(self, values):
        """Update min/max tracking"""
        for i in range(4):
            if values[i] < self.min_vals[i]:
                self.min_vals[i] = values[i]
            if values[i] > self.max_vals[i]:
                self.max_vals[i] = values[i]
    
    def print_status(self, values):
        """Print current values and ranges"""
        print("\033[2J\033[H")  # Clear screen and move cursor to top
        print("🎛️  POTENTIOMETER CALIBRATION TOOL 🎛️")
        print("=" * 60)
        print("Turn each potentiometer FULLY in both directions")
        print("Press Ctrl+C when done to save calibration")
        print("=" * 60)
        print()
        
        for i in range(4):
            range_span = self.max_vals[i] - self.min_vals[i]
            range_percent = (range_span / 65535.0) * 100
            current_percent = ((values[i] - self.min_vals[i]) / max(1, range_span)) * 100 if range_span > 0 else 0
            
            print(f"Pot {i+1} ({self.pot_names[i]}:")
            print(f"  Current: {values[i]:5d} ({current_percent:.1f}%)")
            print(f"  Range:   {self.min_vals[i]:5d} - {self.max_vals[i]:5d} ({range_percent:.1f}% of full scale)")
            print(f"  Span:    {range_span:5d}")
            print()
    
    def save_calibration(self):
        """Save calibration to file for synth to use"""
        calibration = {
            "pot_ranges": [
                {"min": self.min_vals[i], "max": self.max_vals[i], "name": self.pot_names[i]}
                for i in range(4)
            ],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open("pot_calibration.json", "w") as f:
            json.dump(calibration, f, indent=2)
        
        print(f"✅ Calibration saved to pot_calibration.json")
        return calibration
    
    def generate_synth_code(self):
        """Generate code to paste into your synth"""
        print("\n" + "="*60)
        print("📋 CODE TO ADD TO YOUR SYNTH:")
        print("="*60)
        print("Add this to your synth's read_potentiometers_thread() function:")
        print()
        
        for i, name in enumerate(self.pot_names):
            var_name = ["freq_raw", "vol_raw", "wave_raw", "filter_raw"][i]
            min_val = self.min_vals[i]
            max_val = self.max_vals[i]
            
            print(f"# {name} pot (calibrated)")
            print(f"{var_name} = self.pot_{['freq', 'volume', 'wave', 'filter'][i]}.value")
            print(f"{var_name}_norm = ({var_name} - {min_val}) / ({max_val} - {min_val})")
            print(f"{var_name}_norm = max(0, min(1, {var_name}_norm))  # Clamp 0-1")
            print()
    
    def run(self):
        """Run the calibration process"""
        print("🎛️  Starting Potentiometer Calibration")
        print("Move each pot through its full range to calibrate")
        print()
        
        try:
            while True:
                # Read current values
                values = self.read_pots()
                
                # Update min/max tracking
                self.update_ranges(values)
                
                # Display current status
                self.print_status(values)
                
                # Small delay
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n" + "="*60)
            print("🎯 CALIBRATION COMPLETE!")
            print("="*60)
            
            # Save calibration
            calibration = self.save_calibration()
            
            # Show results
            print("\nCalibration Results:")
            for i in range(4):
                range_span = self.max_vals[i] - self.min_vals[i]
                range_percent = (range_span / 65535.0) * 100
                print(f"  {self.pot_names[i]:12}: {self.min_vals[i]:5d} - {self.max_vals[i]:5d} "
                      f"(range: {range_span:5d}, {range_percent:.1f}%)")
            
            # Generate code
            self.generate_synth_code()
            
            print(f"\n✅ Use this calibration in your synth by loading pot_calibration.json")
            print(f"✅ Or copy the code above into your synth's potentiometer reading section")

def main():
    """Main function"""
    calibrator = PotCalibrator()
    calibrator.run()

if __name__ == "__main__":
    main()
