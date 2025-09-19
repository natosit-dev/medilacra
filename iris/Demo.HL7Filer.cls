Class Demo.HL7Filer Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";
Parameter ADAPTER = "";

/// Router/production entry point — calls the existing File() logic
Method OnMessage(pRequest As EnsLib.HL7.Message, Output pResponse As Ens.Response) As %Status
{
    Set pResponse = ##class(Ens.Response).%New()
    Quit ..File(pRequest)
}

ClassMethod File(pHL7 As EnsLib.HL7.Message) As %Status
{
    // locals
    Set ctl="", msgType="", eventTS="", mrn="", pname="", dob="", sex=""
    Set parentId="", sc=$$$OK

    // --- Extract from HL7 ---
    Set ctl     = ..Get(pHL7,"MSH:10")
    Set msgType = ..Get(pHL7,"MSH:9(1).1")_"^"_..Get(pHL7,"MSH:9(1).2")
    Set eventTS = ..HL7TS2ODBC(..Get(pHL7,"MSH:7"))   // "YYYY-MM-DD hh:mm:ss" or ""
    Set mrn     = ..Get(pHL7,"PID:3(1).1")
    Set pname   = ..Get(pHL7,"PID:5(1).1")
    Set dob     = ..HL7DT2ISO(..Get(pHL7,"PID:7"))    // "YYYY-MM-DD" or ""
    Set sex     = ..Get(pHL7,"PID:8")

    // --- Transaction covers parent + children ---
    TSTART

    // Cast NULLIF(...) to ANSI types to avoid -376/-104
  &sql(INSERT INTO Demo.PatientMsg(ControlID,MsgType,EventDT,MRN,PatientName,DOB,Sex)
     VALUES(
         :ctl,
         :msgType,
         CAST(NULLIF(:eventTS,'') AS TIMESTAMP),
         :mrn,
         :pname,
         CAST(NULLIF(:dob,'') AS DATE),
         :sex
     ))

  If SQLCODE<0 {
    TROLLBACK
    Quit $$$ERROR($$$GeneralError,"Insert PatientMsg failed: SQLCODE="_SQLCODE_" "_$zerror)
  }

    // Get the auto-generated identity
    &sql(SELECT LAST_IDENTITY() INTO :parentId)
      If SQLCODE<0 {
        TROLLBACK
        Quit $$$ERROR($$$GeneralError,"Fetching LAST_IDENTITY() failed: SQLCODE="_SQLCODE_" "_$zerror)
  }

    // --- Iterate OBX segments without GetValueCountAt() ---
    Set i=1
OBXLP
    Set setId = ..Get(pHL7,"OBX("_i_"):1")
    If setId="" Goto OBXEND   // no more OBX segments

    Set valType = ..Get(pHL7,"OBX("_i_"):2")
    Set id  = ..Get(pHL7,"OBX("_i_"):3(1).1") // Renamed variable to 'id'
    Set obsText = ..Get(pHL7,"OBX("_i_"):3(1).2")
    Set val = ..Get(pHL7,"OBX("_i_"):5(1).1")
    Set units = ..Get(pHL7,"OBX("_i_"):6(1).1")
    Set refRange = ..Get(pHL7,"OBX("_i_"):7")
    Set abn = ..Get(pHL7,"OBX("_i_"):8")

    &sql(INSERT INTO Demo.Observation(Parent,SetID,Id,Text,ValueType,Value,Units,RefRange,Abnormal)
         VALUES(:parentId,:setId,:id,:obsText,:valType,:val,:units,:refRange,:abn))
    If SQLCODE<0 {
      TROLLBACK
      Quit $$$ERROR($$$GeneralError,"Insert Observation failed (OBX #"_i_"): SQLCODE="_SQLCODE_" "_$zerror)
    }

    Set i=i+1
    Goto OBXLP

OBXEND
    TCOMMIT
    Quit $$$OK
}

ClassMethod Get(pHL7 As EnsLib.HL7.Message, path As %String) As %String
{
    If '$IsObject(pHL7) Quit ""
    Quit pHL7.GetValueAt(path)
}

// HL7 DTM → 'YYYY-MM-DD hh:mm:ss'
ClassMethod HL7TS2ODBC(ts As %String) As %String
{
    If ts="" Quit ""
    Set y=$E(ts,1,4), m=$E(ts,5,6), d=$E(ts,7,8)
    Set hh=$S($L(ts)>=10:$E(ts,9,10),1:"00")
    Set mm=$S($L(ts)>=12:$E(ts,11,12),1:"00")
    Set ss=$S($L(ts)>=14:$E(ts,13,14),1:"00")
    Quit y_"-"_m_"-"_d_" "_hh_":"_mm_":"_ss
}

// HL7 DT → 'YYYY-MM-DD'
ClassMethod HL7DT2ISO(dt As %String) As %String
{
    If dt="" Quit ""
    Quit $E(dt,1,4)_"-"_$E(dt,5,6)_"-"_$E(dt,7,8)
}

}
