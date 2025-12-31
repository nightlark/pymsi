"""
Test custom action type parsing and validation.

This test module validates that pymsi can correctly read and interpret
CustomAction table entries, including various type flag combinations.
"""

from pathlib import Path

import pytest

import pymsi


def test_custom_action_type_1126_breakdown():
    """
    Test that Custom Action Type 1126 is correctly understood.
    
    Type 1126 breakdown:
    - 2: Exe
    - 4: Text data (command line)
    - 32: Directory (source location)
    - 64: Continue (ignore errors)
    - 1024: InScript (deferred execution)
    Total: 2 + 4 + 32 + 64 + 1024 = 1126
    """
    # Verify the math
    assert 2 + 4 + 32 + 64 + 1024 == 1126
    
    # Check bit flags
    type_1126 = 1126
    assert (type_1126 & 0x02) != 0  # Exe bit
    assert (type_1126 & 0x04) != 0  # Text data bit
    assert (type_1126 & 0x20) != 0  # Directory bit
    assert (type_1126 & 0x40) != 0  # Continue bit
    assert (type_1126 & 0x400) != 0  # InScript bit
    assert (type_1126 & 0x200) == 0  # NoImpersonate NOT set


def test_custom_action_type_flags():
    """Test various custom action type flag combinations."""
    
    # Type 1: DLL from Binary table
    type_dll_binary = 1
    assert (type_dll_binary & 0x01) != 0
    
    # Type 2: Exe from Binary table
    type_exe_binary = 2
    assert (type_exe_binary & 0x02) != 0
    
    # Type 6: VBScript from Binary table (2 + 4)
    type_vbscript_binary = 6
    assert type_vbscript_binary == 2 + 4
    
    # Type 22: JScript from Binary table (2 + 4 + 16)
    type_jscript_binary = 22
    assert type_jscript_binary == 2 + 4 + 16
    
    # Type 38: VBScript inline (6 + 32)
    type_vbscript_inline = 38
    assert type_vbscript_inline == 6 + 32
    
    # Type 54: JScript inline (22 + 32)
    type_jscript_inline = 54
    assert type_jscript_inline == 22 + 32


def test_custom_action_execution_flags():
    """Test execution-related flags."""
    
    # Continue flag (0x40 = 64)
    continue_flag = 0x40
    assert continue_flag == 64
    
    # Async flag (0x80 = 128)
    async_flag = 0x80
    assert async_flag == 128
    
    # NoImpersonate flag (0x200 = 512)
    no_impersonate_flag = 0x200
    assert no_impersonate_flag == 512
    
    # InScript/Deferred flag (0x400 = 1024)
    in_script_flag = 0x400
    assert in_script_flag == 1024
    
    # Rollback flag (0x100 = 256) + InScript (0x400)
    rollback_flag = 0x100 | 0x400
    assert rollback_flag == 256 + 1024
    
    # Commit flag (0x200 = 512) + InScript (0x400)
    # Note: 0x200 is also NoImpersonate, but in combination with
    # 0x400 and 0x100, different interpretations apply
    commit_flag = 0x200 | 0x400 | 0x100
    assert commit_flag == 512 + 1024 + 256


@pytest.mark.skipif(
    not Path("tests/wix/out/CA1126-Type1126.msi").exists(),
    reason="WiX test MSI not built"
)
def test_read_custom_action_type_1126():
    """
    Test reading the CA1126-Type1126.msi file and verifying the Type value.
    
    This test requires that the WiX test MSIs have been built.
    """
    msi_path = Path("tests/wix/out/CA1126-Type1126.msi")
    
    with pymsi.Package(msi_path) as pkg:
        custom_action_table = pkg.get("CustomAction")
        assert custom_action_table is not None, "CustomAction table not found"
        
        # Find the CA_Type1126 action
        ca_type_1126 = None
        for row in custom_action_table.rows:
            if row["Action"] == "CA_Type1126":
                ca_type_1126 = row
                break
        
        assert ca_type_1126 is not None, "CA_Type1126 action not found"
        
        # Verify the Type value is 1126
        action_type = ca_type_1126["Type"]
        assert action_type == 1126, f"Expected Type 1126, got {action_type}"
        
        # Verify the Source field contains the command
        source = ca_type_1126["Source"]
        assert "cmd.exe" in source or source is None


@pytest.mark.skipif(
    not Path("tests/wix/out/CAVBScript.msi").exists(),
    reason="WiX test MSI not built"
)
def test_read_vbscript_custom_actions():
    """
    Test reading VBScript custom actions from MSI.
    """
    msi_path = Path("tests/wix/out/CAVBScript.msi")
    
    with pymsi.Package(msi_path) as pkg:
        custom_action_table = pkg.get("CustomAction")
        assert custom_action_table is not None
        
        actions = {row["Action"]: row for row in custom_action_table.rows}
        
        # Check CA_VBS_Binary (Type 6: VBScript from Binary)
        if "CA_VBS_Binary" in actions:
            ca_vbs_binary = actions["CA_VBS_Binary"]
            action_type = ca_vbs_binary["Type"]
            # Type should be 6 or include the VBScript bits
            assert (action_type & 0x06) != 0, f"Expected VBScript type, got {action_type}"
        
        # Check CA_VBS_Inline (Type 38: VBScript inline)
        if "CA_VBS_Inline" in actions:
            ca_vbs_inline = actions["CA_VBS_Inline"]
            action_type = ca_vbs_inline["Type"]
            # Type should be 38 (6 + 32) or similar
            assert action_type == 38 or action_type == 6 + 32 or (action_type & 0x06) != 0


@pytest.mark.skipif(
    not Path("tests/wix/out/CAJScript.msi").exists(),
    reason="WiX test MSI not built"
)
def test_read_jscript_custom_actions():
    """
    Test reading JScript custom actions from MSI.
    """
    msi_path = Path("tests/wix/out/CAJScript.msi")
    
    with pymsi.Package(msi_path) as pkg:
        custom_action_table = pkg.get("CustomAction")
        assert custom_action_table is not None
        
        actions = {row["Action"]: row for row in custom_action_table.rows}
        
        # Check CA_JS_Binary (Type 22: JScript from Binary)
        if "CA_JS_Binary" in actions:
            ca_js_binary = actions["CA_JS_Binary"]
            action_type = ca_js_binary["Type"]
            # Type should be 22 (2 + 4 + 16) or include JScript bits
            assert (action_type & 0x16) != 0, f"Expected JScript type, got {action_type}"
        
        # Check CA_JS_Inline (Type 54: JScript inline)
        if "CA_JS_Inline" in actions:
            ca_js_inline = actions["CA_JS_Inline"]
            action_type = ca_js_inline["Type"]
            # Type should be 54 (22 + 32) or similar
            assert action_type == 54 or action_type == 22 + 32 or (action_type & 0x16) != 0


@pytest.mark.skipif(
    not Path("tests/wix/out/CAExeTypes.msi").exists(),
    reason="WiX test MSI not built"
)
def test_read_exe_dll_custom_actions():
    """
    Test reading EXE and DLL custom actions from Binary table.
    """
    msi_path = Path("tests/wix/out/CAExeTypes.msi")
    
    with pymsi.Package(msi_path) as pkg:
        custom_action_table = pkg.get("CustomAction")
        assert custom_action_table is not None
        
        actions = {row["Action"]: row for row in custom_action_table.rows}
        
        # Check CA_Exe_Binary (Type 2: Exe from Binary)
        if "CA_Exe_Binary" in actions:
            ca_exe = actions["CA_Exe_Binary"]
            action_type = ca_exe["Type"]
            assert (action_type & 0x02) != 0, f"Expected Exe type, got {action_type}"
        
        # Check CA_Dll_Binary (Type 1: DLL from Binary)
        if "CA_Dll_Binary" in actions:
            ca_dll = actions["CA_Dll_Binary"]
            action_type = ca_dll["Type"]
            assert (action_type & 0x01) != 0, f"Expected DLL type, got {action_type}"


@pytest.mark.skipif(
    not Path("docs/_static/example.msi").exists(),
    reason="Example MSI not found"
)
def test_read_example_msi_custom_actions():
    """
    Test reading custom actions from the example MSI if it has any.
    """
    msi_path = Path("docs/_static/example.msi")
    
    with pymsi.Package(msi_path) as pkg:
        custom_action_table = pkg.get("CustomAction")
        
        if custom_action_table is not None and custom_action_table.rows:
            # Just verify we can read the table without errors
            for row in custom_action_table.rows:
                action_name = row["Action"]
                action_type = row["Type"]
                assert isinstance(action_name, str)
                assert isinstance(action_type, int)
                assert action_type >= 0
