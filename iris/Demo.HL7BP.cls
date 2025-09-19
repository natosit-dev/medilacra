Class Demo.HL7BP Extends Ens.BusinessProcess
{
Method OnRequest(pHL7 As EnsLib.HL7.Message, Output pResponse As Ens.Response) As %Status
{
  #dim sc As %Status = $$$OK

  // Pull what we need straight from MSH
  // HL7 version/category (e.g., "2.5" or "2.5.1")
  set msgCat  = pHL7.GetValueAt("MSH:12")
  // Message name (e.g., "ADT_A01", "ORU_R01")
  set msgName = pHL7.GetValueAt("MSH:9.1")_"_"_pHL7.GetValueAt("MSH:9.2")

  // Trace for debugging (avoid calling missing methods)
  $$$TRACE("MSH-derived -> Category="_msgCat_"  DocName="_msgName)

  // (Optional) Branch by message if you need to
  // if (msgName="ORU_R01") { ... } elseif (msgName="ADT_A01") { ... }

  // File the message
  set sc = ##class(Demo.HL7Filer).File(pHL7)
  if $$$ISERR(sc) {
    $$$LOGERROR($System.Status.GetErrorText(sc))
  }

  quit sc
}
}
