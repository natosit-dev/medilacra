Class SDOH.Transform.AddPoliceCountOBX Extends Ens.DataTransform [ Language = objectscript ]
{
ClassMethod Transform(source As EnsLib.HL7.Message, ByRef target As EnsLib.HL7.Message) As %Status
{
    Set tSC = $$$OK
    Set target = source
    Set target.DocType = "2.5:ADT_A01"

    Set cnt = 0
    Set zip = target.GetValueAt("PID:11(1):5")
    If $Length(zip)>0 {
        Try {
            Set cnt = ##class(SDOH.Utils.Police).GetPoliceStationCountByZIP(zip)
        } Catch ex {
            // keep cnt=0
        }
    }

    // OBX|1|NM|ESRI_POLICE_COUNT^Police Station Count^L||<cnt>|||||F
    Set obx = ##class(EnsLib.HL7.Segment).%New()
    Set obxStr = "OBX|1|NM|ESRI_POLICE_COUNT^Police Station Count^L||"_cnt_"|||||F"
    Set sc  = obx.ImportFromString(obxStr, target.Separators)
    If '$SYSTEM.Status.IsOK(sc) Quit sc

    Set idxPV1 = target.GetSegmentIndex("PV1")
    If (idxPV1>0) {
        Do target.InsertSegmentAt(obx, idxPV1+1)
    } Else {
        Do target.AppendSegment(obx)
    }

    Do target.BuildMap(1)

    // FIXED: log a simple string
    Do ##class(Ens.Util.Log).LogInfo("AddPoliceCountOBX ran zip="_zip_" cnt="_cnt)

    Quit tSC
}
}
