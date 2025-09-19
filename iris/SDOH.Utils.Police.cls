Class SDOH.Utils.Police Extends %RegisteredObject
{

ClassMethod GetPoliceStationCountByZIP(zip5 As %String) As %Integer [ ProcedureBlock = 1 ]
{
    Set count=0
    If zip5="" Quit count

    // Build query parts (tolerate ZIP+4 in the layer)
    Set where = "ZIP LIKE '"_zip5_"%'"
    Set stats = "[{""statisticType"":""count"",""onStatisticField"":""OBJECTID"",""outStatisticFieldName"":""station_count""}]"

    // HTTP request
    Set http = ##class(%Net.HttpRequest).%New()
    Set http.Https = 1
    Set http.SSLConfiguration = "default"
    Set http.Server = "services1.arcgis.com"

    // Build path + querystring
    Set path = "/Hp6G80Pky0om7QvQ/ArcGIS/rest/services/Local_Law_Enforcement_Locations/FeatureServer/0/query"
    Set qs = "where="_$ZCONVERT(where,"O","URL")
    Set qs = qs_"&outStatistics="_$ZCONVERT(stats,"O","URL")
    Set qs = qs_"&groupByFieldsForStatistics=ZIP&returnGeometry=false&f=json"

    // Execute
    Set sc = http.Get(path_"?"_qs)
    If ##class(%SYSTEM.Status).IsError(sc) Quit count

    // Read full body
    Set stream = http.HttpResponse.Data, body=""
    For  Set chunk=stream.Read(32767) Quit:chunk=""  Set body=body _ chunk
    If body="" Quit count

    // Parse JSON and extract count
    Try {
        Set json  = {}.%FromJSON(body)
        // If service returned an error JSON, keep count=0 and skip parsing
        If json.%Get("error")'="" {
            // do nothing; count stays 0
        } Else {
            Set feats = json.%Get("features")
            If (feats'="")&&(feats.%IsA("%DynamicArray"))&&(feats.%Size()>0) {
                Set first = feats.%Get(0)
                If first.%IsA("%DynamicObject") {
                    Set attrs = first.%Get("attributes")
                    If attrs'="" {
                        Set count = +attrs.%Get("station_count")
                    }
                }
            }
        }
    } Catch ex {
        // leave count = 0
    }

    Quit count
}

}
