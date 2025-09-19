Class Demo.HL7ToGlobalOp Extends Ens.BusinessOperation
{
Parameter INVOCATION = "Queue";

/// Handles any EnsLib.HL7.Message routed to this operation.
Method OnMessage(pRequest As EnsLib.HL7.Message, Output pResponse As Ens.Response) As %Status
{
    Set sc = $$$OK
    Try {
        // Build a stable key (prefer MSH-10; else job+timestamp)
        Set key = pRequest.GetValueAt("MSH:10")
        If key = "" Set key = $JOB_"-"_$ZDATETIME($HOROLOG,3)

        // Extract MRN (PID-3.1)
        Set mrn = pRequest.GetValueAt("PID:3(1):1")

        // Check previous MRN for this key (before updating)
        Set old = $Get(^DemoHL7MRN(key))

        // Keep hierarchical node (optional but handy)
        Set ^DemoHL7(key,"MRN") = mrn

        // If MRN changed, remove stale reverse mapping
        If old'="", old'=mrn {
            Kill ^DemoHL7KeysByMRN(old,key)
        }

        // Update flat index and reverse index
        If mrn'="" {
            Set ^DemoHL7MRN(key) = mrn
            Set ^DemoHL7KeysByMRN(mrn,key) = 1
        } Else {
            // MRN now blank: clear indexes for this key
            If old'="" Kill ^DemoHL7KeysByMRN(old,key)
            Kill ^DemoHL7MRN(key)
        }

        // Optional response
        Set pResponse = ##class(Ens.Response).%New()
    } Catch ex {
        Set sc = ex.AsStatus()
    }
    Return sc
}
}
