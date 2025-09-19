Class SDOH.BP.AddCommunitySDOH Extends Ens.BusinessProcess
{
Method OnRequest(pHL7 As EnsLib.HL7.Message, Output pResp As EnsLib.HL7.Message) As %Status
{
    Set pResp=pHL7
    // 1) Resolve geography (examples: pull from cached xwalk by ZIP)
    Set zip=pHL7.GetValueAt("PID:11(1):5")
    Quit:zip="" $$$OK
    // TODO: replace with your real lookups:
    Set zcta=zip, countyFIPS=$$LookupCountyFIPS^SDOH.Ref(zip), tract=$$LookupTract^SDOH.Ref(zip)

    // 2) Call APIs
    Set svi=##class(SDOH.Utils.SVI).GetSVIOverallByTract(tract)
    Set unins=##class(SDOH.Utils.Census).GetUninsuredPctByZCTA(zcta)
    Set fqhc=##class(SDOH.Utils.HRSA).GetFQHCSiteCountByCountyFIPS(countyFIPS)

    // 3) Append Z-segments (ZSD-1=code, -2=value, -3=date, -4=source)
    Do ..AddZ(pResp,"SVI_OVERALL",svi,"CDC/ATSDR SVI 2022")
    Do ..AddZ(pResp,"UNINSURED_PCT",unins,"Census ACS S2701")
    Do ..AddZ(pResp,"FQHC_CNT",fqhc,"HRSA Health Center Sites")
    Quit $$$OK
}

ClassMethod AddZ(msg As EnsLib.HL7.Message, code As %String, val As %String, src As %String)
{
    Quit:val=""
    Set seg=##class(EnsLib.HL7.Segment).%New()
    Set seg.SegTypeName="ZSD"
    Do seg.SetValueAt(code,1)
    Do seg.SetValueAt(val,2)
    Do seg.SetValueAt($ZDATE($HOROLOG,8),3)
    Do seg.SetValueAt(src,4)
    Do msg.AppendSegment(seg)
}
}
