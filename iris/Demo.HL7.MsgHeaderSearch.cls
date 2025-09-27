Class Demo.HL7.MsgHeaderSearch Extends Ens.SearchTable
{
Parameter MESSAGECLASS = "EnsLib.HL7.Message";

Index MSH10 On {MSH:10};  // Message Control ID
Index MSH7  On {MSH:7};   // Date/Time of Message
Index PID3  On {PID:3};   // Patient Identifier
Index PID7  On {PID:7};   // DOB
Index PID8  On {PID:8};   // Sex
}
