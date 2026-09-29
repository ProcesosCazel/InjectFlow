from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from app.errors import SourceDataError
from app.jupiter_xml_parser import JupiterXmlParser


def _write_xml(tmp_path: Path, variables: dict[str, object], *, comment: str = "1689 test") -> Path:
    root = ET.Element(
        "HMI_Data",
        {"Version": "1.2", "MaschinenNR.": "XXXXXX", "Date": "28-09-2026"},
    )
    ET.SubElement(root, "Comment", {"Text": comment})
    group = ET.SubElement(root, "VarGroup", {"Name": "VG_MoldData"})
    for name, value in variables.items():
        node = ET.SubElement(group, "Variable", {"Name": name})
        child = ET.SubElement(node, "Value")
        child.text = "true" if value is True else "false" if value is False else str(value)
    path = tmp_path / "mold.xml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def _value(records, key):
    return records[key][0].raw_value


def _approx(value, expected, abs_tol=1e-6):
    assert float(value) == pytest.approx(float(expected), abs=abs_tol)


def test_jupiter_xml_metadata_and_hrs_are_normalized(tmp_path: Path):
    path = _write_xml(
        tmp_path,
        {
            "HeatingMold1.sv_ZoneRetain1.bUsed": True,
            "HeatingMold1.sv_ZoneRetain1.rSetValVis": 260,
            "HeatingMold1.sv_ZoneRetain2.bUsed": False,
            "HeatingMold1.sv_ZoneRetain2.rSetValVis": 240,
        },
    )
    parser = JupiterXmlParser()
    records = parser.parse(path)

    assert parser.version == "1.2"
    assert parser.export_date == "28-09-2026"
    assert parser.mold_number == "1689"
    assert parser.active_hrs_zones == (1,)
    assert _value(records, "Jupiter.HRSZone1Mode") == Decimal(1)
    assert _value(records, "Jupiter.HRSZone2Mode") == Decimal(0)
    assert _value(records, "Jupiter.HRSZone1Temp") == Decimal(260)
    assert _value(records, "Jupiter.HRSTotalZonesText") == "TOTAL: 1 ZONAS"


def test_jupiter_mold_close_uses_next_point_endpoint_and_derives_clamp_force(tmp_path: Path):
    variables = {
        "Mold1.sv_MoldCloseIntelligenceSet.bUseIntelligence": False,
        "Mold1.sv_MoldFwdProfVisSrc.Profile.iNoOfPoints": 5,
        "Mold1.sv_ClampForce.rSetClampForce": 2942,
        "Mold1.sv_rSetClampPres": 176.2963,
        "MoldLock1.sv_rHiPressureVelocityVis": 20,
        "Mold1.sv_rMoldProtectForce": 6,
        "Mold1.sv_dMoldProtectTimeSet": 2_000_000,
    }
    for point, pressure, velocity, pos in [
        (15, 90, 487.35, 1464.22),
        (16, 85, 433.2, 600),
        (17, 85, 400.71, 200),
        (18, 105.337074, 303.24, 80),
        (19, 176.2963, 0, 0),
    ]:
        variables[f"Mold1.sv_MoldFwdProfVisSrc.Profile.Points[{point}].rPressure"] = pressure
        variables[f"Mold1.sv_MoldFwdProfVisSrc.Profile.Points[{point}].rVelocity"] = velocity
        variables[f"Mold1.sv_MoldFwdProfVisSrc.Profile.Points[{point}].rStartPos"] = pos

    records = JupiterXmlParser(machine="309").parse(_write_xml(tmp_path, variables))
    assert _value(records, "Jupiter.MoldCloseStages") == Decimal(3)
    _approx(_value(records, "Jupiter.MoldCloseStage1Velocity"), 45)
    assert _value(records, "Jupiter.MoldCloseStage1Position") == Decimal(600)
    assert _value(records, "Jupiter.MoldCloseStage2Position") == Decimal(200)
    assert _value(records, "Jupiter.MoldCloseStage3Position") == Decimal(80)
    assert _value(records, "Jupiter.MoldProtectStagePosition") == Decimal(0)
    assert _value(records, "Jupiter.MoldProtectionTime") == Decimal(2)
    _approx(_value(records, "Jupiter.MoldClampTons"), 800, 1e-3)


def test_jupiter_mold_open_separates_mould_and_fixed_end(tmp_path: Path):
    variables = {
        "Mold1.sv_MoldOpenIntelligenceSet.bUseIntelligence": False,
        "Mold1.sv_MoldBwdProfVis.Profile.iNoOfPoints": 5,
        "MoldTieBars1.sv_MoldLockBwdConstVis[5].Pressure.Output.rOutputValue": 10,
        "MoldTieBars1.sv_MoldLockBwdConstVis[5].Velocity.Output.rOutputValue": 5,
        "MoldTieBars1.sv_MoldLockBwdPosition": 10,
    }
    # 309-style 1,2,3,4,End.  Destination/To is the next point start position.
    for point, pressure, velocity, pos in [
        (1, 80, 545, 0),
        (2, 80, 436, 200),
        (3, 80, 381.5, 250),
        (4, 80, 327, 850),
        (5, 30, 218, 900),
        (6, 0, 0, 965),
    ]:
        variables[f"Mold1.sv_MoldBwdProfVis.Profile.Points[{point}].rPressure"] = pressure
        variables[f"Mold1.sv_MoldBwdProfVis.Profile.Points[{point}].rVelocity"] = velocity
        variables[f"Mold1.sv_MoldBwdProfVis.Profile.Points[{point}].rStartPos"] = pos

    records = JupiterXmlParser(machine="309").parse(_write_xml(tmp_path, variables))
    assert _value(records, "Jupiter.MoldOpenStages") == Decimal(5)
    assert _value(records, "Jupiter.MoldOpenMouldPressure") == Decimal(10)
    assert _value(records, "Jupiter.MoldOpenMouldVelocity") == Decimal(5)
    assert _value(records, "Jupiter.MoldOpenMouldPosition") == Decimal(10)
    _approx(_value(records, "Jupiter.MoldOpenStage1Velocity"), 50)
    assert _value(records, "Jupiter.MoldOpenStage1Position") == Decimal(200)
    assert _value(records, "Jupiter.MoldOpenStage4Position") == Decimal(900)
    _approx(_value(records, "Jupiter.MoldOpenEndVelocity"), 20)
    assert _value(records, "Jupiter.MoldOpenEndPosition") == Decimal(965)
    assert _value(records, "Jupiter.MoldOpenMaxReleasePressure") == Decimal(10)


def test_jupiter_injection_and_hold_use_screw_geometry_and_fixed_end(tmp_path: Path):
    variables = {
        "Injection1.sv_InjectProfVis.Profile.iNoOfPoints": 2,
        "Injection1.sv_InjectProfVis.Profile.Points[1].rPressure": 200.81632,
        "Injection1.sv_InjectProfVis.Profile.Points[1].rVelocity": 115.45353,
        "Injection1.sv_InjectProfVis.Profile.Points[1].rStartPos": 0,
        "Injection1.sv_InjectProfVis.Profile.Points[2].rPressure": 188.2653,
        "Injection1.sv_InjectProfVis.Profile.Points[2].rVelocity": 76.96902,
        "Injection1.sv_InjectProfVis.Profile.Points[2].rStartPos": 192.42255,
        "Injection1.sv_InjectProfVis.Profile.Points[3].rStartPos": -1000,
        "Injection1.sv_CutOffParams.rPositionThreshold": 96.211275,
        "Injection1.sv_CutOffParams.dTimeThreshold": 5_500_000,
        "Injection1.sv_CutOffParams.rInjectPressureThreshold": 251.0204,
        "Injection1.sv_InjectTimesSet.dMaxMoveTime": 15_000_000,
        "Injection1.sv_HoldProfVis.Profile.iNoOfPoints": 1,
        "Injection1.sv_HoldProfVis.Profile.Points[1].rPressure": 62.7551,
        "Injection1.sv_HoldProfVis.Profile.Points[1].rVelocity": 38.48451,
        "Injection1.sv_HoldProfVis.Profile.Points[1].rStartPos": 0,
        "Injection1.sv_HoldProfVis.Profile.Points[2].rStartPos": 3,
    }
    records = JupiterXmlParser(machine="309").parse(_write_xml(tmp_path, variables))

    assert _value(records, "Jupiter.Injection1Stages") == Decimal(2)
    _approx(_value(records, "Jupiter.Injection1Stage1Pressure"), 80, 2e-4)
    _approx(_value(records, "Jupiter.Injection1Stage1Velocity"), 30, 2e-5)
    _approx(_value(records, "Jupiter.Injection1Stage1Position"), 50, 2e-5)
    assert "Jupiter.Injection1EndPosition" not in records
    _approx(_value(records, "Jupiter.Injection1ScrewPosition"), 25, 2e-5)
    assert _value(records, "Jupiter.Injection1TimeSet") == Decimal("5.5")
    _approx(_value(records, "Jupiter.Injection1PressureSet"), 100, 2e-4)

    assert _value(records, "Jupiter.Holding1Stages") == Decimal(1)
    _approx(_value(records, "Jupiter.Hold1EndPressure"), 25, 2e-4)
    _approx(_value(records, "Jupiter.Hold1EndVelocity"), 10, 2e-5)
    assert _value(records, "Jupiter.Hold1EndTime") == Decimal(3)


def test_jupiter_charge_display_uses_machine_hmi_rotation_transform(tmp_path: Path):
    variables = {
        "Injection2.sv_PlastProfVis.Profile.iNoOfPoints": 1,
        "Injection2.sv_PlastProfVis.Profile.Points[1].rPressure": 90,
        "Injection2.sv_PlastProfVis.Profile.Points[1].rRotation": 57.595867,
        "Injection2.sv_PlastProfVis.Profile.Points[1].rBackPressure": 5,
        "Injection2.sv_PlastProfVis.Profile.Points[2].rStartPos": 186.53206,
    }
    path = _write_xml(tmp_path, variables)
    rpm_308 = _value(JupiterXmlParser(machine="308B").parse(path), "Jupiter.Charge2EndRPM")
    rpm_309 = _value(JupiterXmlParser(machine="309").parse(path), "Jupiter.Charge2EndRPM")
    _approx(rpm_308, 100, 2e-5)
    _approx(rpm_309, 220, 4e-5)

    with pytest.raises(SourceDataError, match="selected machine"):
        JupiterXmlParser().parse(path)


def test_jupiter_308b_uses_relative_injection_and_decomp_speed_transforms(tmp_path: Path):
    variables = {
        "Injection1.sv_InjectProfVis.Profile.iNoOfPoints": 1,
        "Injection1.sv_InjectProfVis.Profile.Points[1].rPressure": 200.81632,
        "Injection1.sv_InjectProfVis.Profile.Points[1].rVelocity": 35.40575,
        "Injection1.sv_InjectProfVis.Profile.Points[2].rStartPos": -1000,
        "Injection1.sv_HoldProfVis.Profile.iNoOfPoints": 1,
        "Injection1.sv_HoldProfVis.Profile.Points[1].rPressure": 62.7551,
        "Injection1.sv_HoldProfVis.Profile.Points[1].rVelocity": 30.97999,
        "Injection1.sv_HoldProfVis.Profile.Points[2].rStartPos": 3,
        "Injection1.sv_DecompBefPlastSettings.Mode": 0,
        "Injection1.sv_DecompAftPlastSettings.Mode": 2,
        "Injection1.sv_DecompAftPlastSettings.ConstOutput.Pressure.Output.rOutputValue": 15,
        "Injection1.sv_DecompAftPlastSettings.ConstOutput.Velocity.Output.rOutputValue": 15,
        "Injection1.sv_DecompAftPlastSettings.rDecompPos": 19.242256,
        "Injection1.sv_DecompAftPlastSettings.dDecompTime": 0,
    }
    records = JupiterXmlParser(machine="308B").parse(_write_xml(tmp_path, variables))
    _approx(_value(records, "Jupiter.Injection1EndVelocity"), 8, 2e-4)
    _approx(_value(records, "Jupiter.Hold1EndVelocity"), 7, 2e-4)
    _approx(_value(records, "Jupiter.Decomp1Velocity"), 10, 1e-6)


def test_jupiter_cores_use_coredata_modes_and_do_not_fake_inactive_states(tmp_path: Path):
    variables = {
        "Core1.sv_CoreMode.CoreType": 1,
        "Core1.sv_CoreMode.CoreControlIn": 2,
        "Core1.sv_CoreMode.CoreControlOut": 1,
        "CentralCoordination1.sv_CoreData[1].InMode": 0,
        "CentralCoordination1.sv_CoreData[1].OutMode": 2,
        "Core1.sv_CoreOutput.NormalIn.Pressure.Output.rOutputValue": 80,
        "Core1.sv_CoreOutput.NormalIn.Velocity.Output.rOutputValue": 52.640003,
        "Core1.sv_CoreOutput.NormalOut.Pressure.Output.rOutputValue": 51,
        "Core1.sv_CoreOutput.NormalOut.Velocity.Output.rOutputValue": 26.320002,
        "Core1.sv_CoreSetTimes.MoveIn.dSetDelayTime": 1_000_000,
        "Core1.sv_CoreSetTimes.MoveIn.dSetMoveTime": 2_000_000,
        "Core1.sv_CoreSetTimes.MoveOut.dSetDelayTime": 5_500_000,
        "Core1.sv_CoreSetTimes.MoveOut.dSetMoveTime": 1_500_000,
        # Core B is physically inactive but has zero/default state codes.
        "Core2.sv_CoreMode.CoreType": 0,
        "Core2.sv_CoreMode.CoreControlIn": 0,
        "Core2.sv_CoreMode.CoreControlOut": 0,
        "CentralCoordination1.sv_CoreData[2].InMode": 0,
        "CentralCoordination1.sv_CoreData[2].OutMode": 0,
    }
    parser = JupiterXmlParser()
    records = parser.parse(_write_xml(tmp_path, variables))

    assert parser.active_cores == ("A",)
    assert _value(records, "Jupiter.CoreAMode") == Decimal(1)
    assert _value(records, "Jupiter.CoreAInType") == Decimal(2)
    assert _value(records, "Jupiter.CoreAOutType") == Decimal(1)
    assert _value(records, "Jupiter.CoreAInMode") == Decimal(0)
    assert _value(records, "Jupiter.CoreAOutMode") == Decimal(2)
    _approx(_value(records, "Jupiter.CoreAInVelocity"), 20, 5e-6)
    _approx(_value(records, "Jupiter.CoreAOutVelocity"), 10, 5e-6)
    assert _value(records, "Jupiter.CoreBMode") == Decimal(0)
    for key in ("CoreBInType", "CoreBOutType", "CoreBInMode", "CoreBOutMode"):
        assert f"Jupiter.{key}" not in records


def test_jupiter_valve_gate_numbering_modes_and_injection_codes_are_direct(tmp_path: Path):
    variables = {
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].bUsed": True,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].OpenMode": 0,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].CloseMode": 1,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].injection": 0,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].rStartPos": 38.48451,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].rStopPos": 19.242255,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].dStartDelay": 1_000_000,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].dStopDelay": 2_000_000,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].bActivOnHold": True,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].dHoldDelay": 0,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[9].dHoldActTime": 5_000_000,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[13].bUsed": True,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[13].OpenMode": 1,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[13].CloseMode": 1,
        "ValveGate1.sv_ValveGateData.ValveGateDataArray[13].injection": 1,
    }
    parser = JupiterXmlParser()
    records = parser.parse(_write_xml(tmp_path, variables))

    assert parser.active_valve_gates == (9, 13)
    assert _value(records, "Jupiter.ValveGate9StartCon") == Decimal(0)
    assert _value(records, "Jupiter.ValveGate9StopCon") == Decimal(1)
    assert _value(records, "Jupiter.ValveGate9InjectionNo") == Decimal(0)
    _approx(_value(records, "Jupiter.ValveGate9OnStroke"), 10, 2e-5)
    _approx(_value(records, "Jupiter.ValveGate9OffInjectionStroke"), 5, 2e-5)
    assert _value(records, "Jupiter.ValveGate13InjectionNo") == Decimal(1)


def test_jupiter_first_five_barrel_zones_are_physical_and_fixed_template_fields_are_not_emitted(tmp_path: Path):
    variables = {}
    for unit in (1, 2):
        for zone in range(1, 7):
            variables[f"HeatingNozzle{unit}.sv_ZoneRetain{zone}.rSetValVis"] = 200 + 10 * zone
            variables[f"HeatingNozzle{unit}.sv_ZoneRetain{zone}.ModeVis"] = 0 if zone == 3 else 3
    records = JupiterXmlParser().parse(_write_xml(tmp_path, variables))

    for unit in (1, 2):
        for zone in range(1, 6):
            assert _value(records, f"Jupiter.Barrel{unit}Zone{zone}Mode") == Decimal(1)
            assert _value(records, f"Jupiter.Barrel{unit}Zone{zone}Temp") == Decimal(200 + 10 * zone)
        assert f"Jupiter.Barrel{unit}Zone6Temp" not in records
        assert f"Jupiter.Barrel{unit}CoolPreventTime" not in records
        for zone in range(1, 6):
            assert f"Jupiter.Barrel{unit}Zone{zone}UpperTol" not in records
            assert f"Jupiter.Barrel{unit}Zone{zone}LowerTol" not in records
    assert "Jupiter.RotaryFastPressure" not in records
    assert "Jupiter.RotaryFastVelocity" not in records


def test_jupiter_template_limit_blocks_active_hrs_above_54(tmp_path: Path):
    path = _write_xml(
        tmp_path,
        {
            "HeatingMold1.sv_ZoneRetain55.bUsed": True,
            "HeatingMold1.sv_ZoneRetain55.rSetValVis": 260,
        },
    )
    with pytest.raises(SourceDataError, match="fuera del limite"):
        JupiterXmlParser().parse(path)


@pytest.mark.parametrize("bad", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_jupiter_rejects_nonfinite_numeric_values(tmp_path: Path, bad: str):
    path = _write_xml(tmp_path, {"HeatingNozzle1.sv_ZoneRetain1.rSetValVis": bad})
    with pytest.raises(SourceDataError, match="Invalid numeric value"):
        JupiterXmlParser().parse(path)


@pytest.mark.parametrize("bad", ["1.5", "NaN", "Infinity"])
def test_jupiter_rejects_fractional_or_nonfinite_stage_count(tmp_path: Path, bad: str):
    path = _write_xml(tmp_path, {"Injection1.sv_InjectProfVis.Profile.iNoOfPoints": bad})
    with pytest.raises(SourceDataError, match="Invalid integer value"):
        JupiterXmlParser().parse(path)


def test_jupiter_rejects_conflicting_duplicate_variables(tmp_path: Path):
    root = ET.Element("HMI_Data", {"Version": "1.2"})
    group = ET.SubElement(root, "VarGroup", {"Name": "VG_MoldData"})
    for value in ("1", "2"):
        node = ET.SubElement(group, "Variable", {"Name": "Same.Key"})
        ET.SubElement(node, "Value").text = value
    path = tmp_path / "duplicate.xml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

    with pytest.raises(SourceDataError, match="conflicting duplicate"):
        JupiterXmlParser().parse(path)


def test_jupiter_transfer_switches_decomp_activity_and_rotary_hold_clamp_are_emitted(tmp_path: Path):
    variables = {
        "Injection1.sv_CutOffParams.bUsePosition": True,
        "Injection1.sv_CutOffParams.bUseTimer": False,
        "Injection1.sv_CutOffParams.bUseInjectPressure": False,
        "Injection2.sv_CutOffParams.bUsePosition": True,
        "Injection2.sv_CutOffParams.bUseTimer": True,
        "Injection2.sv_CutOffParams.bUseInjectPressure": False,
        "Injection1.sv_DecompAftPlastSettings.Mode": 0,
        "Injection2.sv_DecompAftPlastSettings.Mode": 2,
        "RotatePlaten1.sv_ConstClamp.Velocity.Output.rOutputValue": 60,
        "RotatePlaten1.sv_dRotClampTime": 600_000,
        "RotatePlaten1.sv_ConstHold.Velocity.Output.rOutputValue": 50,
        "RotatePlaten1.sv_dRotHoldTime": 600_000,
    }
    records = JupiterXmlParser().parse(_write_xml(tmp_path, variables))

    assert _value(records, "Jupiter.Injection1UsePosition") == Decimal(1)
    assert _value(records, "Jupiter.Injection1UseTimer") == Decimal(0)
    assert _value(records, "Jupiter.Injection1UsePressure") == Decimal(0)
    assert _value(records, "Jupiter.Injection2UsePosition") == Decimal(1)
    assert _value(records, "Jupiter.Injection2UseTimer") == Decimal(1)
    assert _value(records, "Jupiter.Injection2UsePressure") == Decimal(0)
    assert _value(records, "Jupiter.Decomp1AfterActive") == Decimal(0)
    assert _value(records, "Jupiter.Decomp2AfterActive") == Decimal(1)
    assert _value(records, "Jupiter.RotaryClampVelocity") == Decimal(60)
    assert _value(records, "Jupiter.RotaryClampTime") == Decimal("0.6")
    assert _value(records, "Jupiter.RotaryHoldVelocity") == Decimal(50)
    assert _value(records, "Jupiter.RotaryHoldTime") == Decimal("0.6")
