Class SDOH.Utils.Http Extends %RegisteredObject
{
ClassMethod Get(url As %String, ByRef body As %String, headers As %String = "") As %Status
{
    Set http=##class(%Net.HttpRequest).%New()
    Set http.Https=($Extract(url,1,5)="https")
    // Optional headers: "Name:Value||Name2:Value2"
    If headers'="" {
        For i=1:1:$Length(headers,"||") {
            Set h=$Piece(headers,"||",i) Quit:h=""
            Do http.SetHeader($Piece(h,":",1),$Piece(h,":",2,*))
        }
    }
    Set tSC=http.Get(url)
    If $$$ISERR(tSC) Quit tSC
    Set body=http.HttpResponse.Data.Read()
    Quit $$$OK
}
}
