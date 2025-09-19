Class SDOH.Utils.Census Extends %RegisteredObject
{
ClassMethod GetUninsuredPctByZCTA(zcta As %String, year As %Integer = 2023, ByRef pStatus As %Status = $$$OK) As %Float
{
    Set base="https://api.census.gov/data/"_year_"/acs/acs5/subject"
    Set qs="?get=S2701_C05_001E&for=zip%20code%20tabulation%20area:"_zcta
    Set tSC=##class(SDOH.Utils.Http).Get(base_qs,.body), pStatus=tSC  If $$$ISERR(tSC) Quit ""
    // JSON: [ ["S2701_C05_001E","zip code tabulation area"], ["7.9","02138"] ]
    Set arr={}.%FromJSON(body) If 'arr.%IsA("%DynamicArray") Quit ""
    If arr.%Size()<2 Quit ""
    Quit +arr.%Get(1).%Get(0)
}
}
