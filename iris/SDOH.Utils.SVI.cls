Class SDOH.Utils.SVI Extends %RegisteredObject
{
ClassMethod GetSVIOverallByTract(tractGEOID As %String) As %Float
{
    Set base="https://onemap.cdc.gov/onemapservices/rest/services/SVI/CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer/2/query"
    Set qs="?where=FIPS%3D%27"_$ZCONVERT(tractGEOID,"O","URL")_"%27&outFields=FIPS%2CRPL_THEMES&f=json"
    Set tSC=##class(SDOH.Utils.Http).Get(base_qs,.body), pStatus=tSC  If $$$ISERR(tSC) Quit ""
    Set json={}.%FromJSON(body)
    If '$IsObject(json.features) Quit ""
    If json.features.%Size()=0 Quit ""
    Quit +json.features.%Get(0).attributes.RPL_THEMES  // 0..1
}
}
