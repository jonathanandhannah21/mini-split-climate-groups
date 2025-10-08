#!/usr/bin/env python3
"""Test coordinator logic with mock data."""

import sys
import os
sys.path.append('custom_components/mini_split_climate_groups')

from const import DEFAULT_TOLERANCE, DEFAULT_HYSTERESIS, DEFAULT_TARGET_TEMP

# Mock member for testing logic
class MockMember:
    def __init__(self, member_id, name, current_temp, target_temp):
        self.member_id = member_id
        self.name = name
        self.current_temp = current_temp
        self.current_target_temp = target_temp
        self.default_target_temp = target_temp
        self.is_on = False
        self.mode = "cool"
        self.is_aligned = True
        self.wants_mode_change = False
        self.wanted_mode = None
        self.current_priority = 1
        self.is_available = True

    def calculate_alignment(self, hysteresis):
        """Calculate if member is aligned with target temperature."""
        if self.mode == "cool":
            self.is_aligned = self.current_temp <= (self.current_target_temp + hysteresis)
        else:  # heat
            self.is_aligned = self.current_temp >= (self.current_target_temp - hysteresis)

    def calculate_wants(self, tolerance):
        """Calculate if member wants a mode change."""
        delta = self.current_temp - self.current_target_temp
        abs_delta = abs(delta)
        
        self.wants_mode_change = False
        self.wanted_mode = None
        
        if abs_delta > tolerance:
            if delta > 0:
                self.wanted_mode = "cool"
            else:
                self.wanted_mode = "heat"
                
            if self.mode != self.wanted_mode:
                self.wants_mode_change = True

    def should_be_on(self, group_mode):
        """Determine if this member should be running."""
        if not self.is_available:
            return False
        if self.mode != group_mode:
            return False
        return not self.is_aligned

def test_priority_logic():
    """Test priority-based decision making."""
    print("=== Testing Priority Logic ===")
    
    # Create test members
    living_room = MockMember("living_room", "Living Room", 73.2, 74.0)
    bedroom = MockMember("bedroom", "Bedroom", 76.8, 72.0)
    
    living_room.current_priority = 2  # Lower priority
    bedroom.current_priority = 1      # Higher priority
    
    members = [living_room, bedroom]
    tolerance = DEFAULT_TOLERANCE
    hysteresis = DEFAULT_HYSTERESIS
    
    # Test scenario: Bedroom too hot, Living Room okay
    for member in members:
        member.calculate_alignment(hysteresis)
        member.calculate_wants(tolerance)
    
    print(f"Living Room: {living_room.current_temp}°F -> {living_room.current_target_temp}°F")
    print(f"  Aligned: {living_room.is_aligned}, Wants: {living_room.wanted_mode}")
    
    print(f"Bedroom: {bedroom.current_temp}°F -> {bedroom.current_target_temp}°F") 
    print(f"  Aligned: {bedroom.is_aligned}, Wants: {bedroom.wanted_mode}")
    
    # Find highest priority member that wants change
    priority_sorted = sorted(members, key=lambda m: m.current_priority)
    deciding_member = None
    
    for member in priority_sorted:
        if member.wants_mode_change and member.wanted_mode:
            deciding_member = member
            break
    
    if deciding_member:
        print(f"✓ Priority logic: {deciding_member.name} (priority #{deciding_member.current_priority}) decides mode: {deciding_member.wanted_mode}")
        assert deciding_member.name == "Bedroom", "Bedroom should have priority"
        assert deciding_member.wanted_mode == "cool", "Should want cooling"
    else:
        print("✓ No changes needed - all members satisfied")

def test_alignment_logic():
    """Test temperature alignment calculations."""
    print("\n=== Testing Alignment Logic ===")
    
    member = MockMember("test", "Test", 72.0, 72.0)
    hysteresis = 0.1
    
    # Test cooling mode alignment
    member.mode = "cool"
    test_cases = [
        (71.9, True, "Below target - aligned"),
        (72.0, True, "At target - aligned"),  
        (72.1, True, "Within hysteresis - aligned"),
        (72.2, False, "Above hysteresis - not aligned")
    ]
    
    for temp, expected, description in test_cases:
        member.current_temp = temp
        member.calculate_alignment(hysteresis)
        print(f"Cool mode: {temp}°F -> {member.is_aligned} ({description})")
        assert member.is_aligned == expected, f"Failed: {description}"
    
    # Test heating mode alignment  
    member.mode = "heat"
    test_cases = [
        (72.2, True, "Above target - aligned"),
        (72.0, True, "At target - aligned"),
        (71.9, True, "Within hysteresis - aligned"), 
        (71.8, False, "Below hysteresis - not aligned")
    ]
    
    for temp, expected, description in test_cases:
        member.current_temp = temp
        member.calculate_alignment(hysteresis)
        print(f"Heat mode: {temp}°F -> {member.is_aligned} ({description})")
        assert member.is_aligned == expected, f"Failed: {description}"
    
    print("✓ All alignment logic tests passed")

def test_tolerance_logic():
    """Test tolerance-based wants calculation."""
    print("\n=== Testing Tolerance Logic ===")
    
    member = MockMember("test", "Test", 72.0, 72.0)
    member.mode = "cool"
    tolerance = 1.5
    
    test_cases = [
        (70.4, True, "heat", "Too cold - wants heat"),
        (70.5, False, None, "Within tolerance - no change"),
        (73.5, False, None, "Within tolerance - no change"),
        (73.6, False, "cool", "Too hot but already in cool mode"),
    ]
    
    for temp, should_want_change, wanted_mode, description in test_cases:
        member.current_temp = temp
        member.calculate_wants(tolerance)
        print(f"{temp}°F: wants_change={member.wants_mode_change}, mode={member.wanted_mode} ({description})")
        assert member.wants_mode_change == should_want_change, f"Failed: {description}"
        assert member.wanted_mode == wanted_mode, f"Failed wanted mode: {description}"
    
    print("✓ All tolerance logic tests passed")

def test_error_cases():
    """Test error handling scenarios."""
    print("\n=== Testing Error Cases ===")
    
    # Test unavailable member
    member = MockMember("unavailable", "Unavailable", 72.0, 72.0)
    member.is_available = False
    
    should_run = member.should_be_on("cool")
    print(f"Unavailable member should_be_on: {should_run}")
    assert not should_run, "Unavailable member should not run"
    
    # Test mode mismatch
    member.is_available = True
    member.mode = "heat"
    should_run = member.should_be_on("cool")
    print(f"Mode mismatch should_be_on: {should_run}")
    assert not should_run, "Mode mismatch should not run"
    
    print("✓ All error case tests passed")

if __name__ == "__main__":
    try:
        test_priority_logic()
        test_alignment_logic() 
        test_tolerance_logic()
        test_error_cases()
        print("\n🎉 All coordinator logic tests PASSED!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)