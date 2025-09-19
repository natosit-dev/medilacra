Class SDOH.DTL.Add.ZPS Extends Ens.DataTransformDTL
{

XData DTL [ XMLNamespace = "http://www.intersystems.com/dtl" ]
{
<transform sourceClass='EnsLib.HL7.Message' targetClass='EnsLib.HL7.Message' language='objectscript'>
  <!-- copy source -> target -->
  <assign value='source' property='target'/>
  <!-- ensure the custom schema DocType is carried forward -->
  <assign value='"SDOH:ADT_A01"' property='target.DocType'/>

  <code><![CDATA[
Set zip=target.GetValueAt("PID:11(1):5")
Set:zip'="" cnt=##class(SDOH.Utils.Police).GetPoliceStationCountByZIP(zip)
Do:zip'="" target.InsertSegment("ZPS")        ; or: target.InsertSegmentAt("ZPS","PID")
Do:zip'="" target.SetValueAt(cnt,"ZPS:1")
]]></code>
</transform>
}
}
