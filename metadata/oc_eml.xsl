<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" 
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0">

    <xsl:output method="html" indent="yes" encoding="UTF-8" />
	<xsl:param name="indent" select="''"/> <!-- Default parameter for indentation -->
	
    <xsl:template match="/eml:eml">
		<xsl:apply-templates select="dataset"/>
		
		<h2>Additional Metadata</h2>
		<xsl:for-each select="additionalMetadata/metadata">
			<p><b>Metadata Type: </b> <xsl:value-of select="@id" /></p>
			<xsl:if test="unitList">
				<h3>Unit List</h3>
				<ul>
					<xsl:for-each select="unitList/unit">
						<li>
							<b><xsl:value-of select="@name" /></b>: 
							<xsl:value-of select="description" />
						</li>
					</xsl:for-each>
				</ul>
			</xsl:if>
			<xsl:if test="emlEditor">
				<h3>EML Editor</h3>
				<p><b>App: </b> <xsl:value-of select="emlEditor/app" /></p>
				<p><b>Release: </b> <xsl:value-of select="emlEditor/release" /></p>
			</xsl:if>
			<xsl:if test="agencyOriginated">
				<h3>Agency Originated</h3>
				<p><b>Agency: </b> <xsl:value-of select="agencyOriginated/agency" /></p>
				<p><b>By or For NPS: </b> <xsl:value-of select="agencyOriginated/byOrForNPS" /></p>
			</xsl:if>
		</xsl:for-each>
	</xsl:template>
	
	<xsl:template match="dataset">
        <html>
            <head>
                <title>
                    <xsl:value-of select="title" />
                </title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    h1 { color: #2e6c80; }
                    h2, h3 { color: #4d4d4d; }
                    ul { list-style-type: disc; margin-left: 20px; }
                    p { margin: 8px 0; }
                    table { border-collapse: collapse; width: 100%; margin-top: 10px; }
                    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
                    th { background-color: #f2f2f2; }
                </style>
            </head>
            <body>
                <h1><xsl:value-of select="title" /></h1>

                <h2>Abstract</h2>
                <xsl:for-each select="abstract/para">
                    <p><xsl:value-of select="normalize-space()" /></p>
                </xsl:for-each>

                <h2>Creators</h2>
                <ul>
                    <xsl:for-each select="creator">
                        <li>
                            <xsl:value-of select="individualName/givenName" /> 
							<xsl:text> </xsl:text> <!-- space to separate first/last name -->
                            <xsl:value-of select="individualName/surName" /> - 
                            <xsl:value-of select="organizationName" />, 
							<xsl:value-of select="positionName" />, 
							<xsl:value-of select="electronicMailAddress" />
                        </li>
                    </xsl:for-each>
                </ul>

				<h2>Associated Parties</h2>
				<ul>
					<xsl:for-each select="associatedParty">
						<li>
							<xsl:value-of select="individualName/givenName" /> 
							<xsl:text> </xsl:text> 
							<xsl:value-of select="individualName/surName" /> - 
							<xsl:value-of select="organizationName" /> (<xsl:value-of select="role" />)
						</li>
					</xsl:for-each>
				</ul>

				<h2>Metadata Provider</h2>
				<ul>
					<xsl:for-each select="metadataProvider">
						<li>
							<xsl:value-of select="individualName/givenName" /> 
							<xsl:text> </xsl:text> 
							<xsl:value-of select="individualName/surName" /> - 
							<xsl:value-of select="organizationName" />, 
							<xsl:value-of select="positionName" />, 
							<xsl:value-of select="electronicMailAddress" />
						</li>
					</xsl:for-each>
				</ul>

				<h2>Publication Date</h2>
				<p><b>Date Published: </b> 
					<xsl:value-of select="string(pubDate)" />
				</p>
				
				<h2>Language</h2>
				<p><b>Language: </b> 
					<xsl:value-of select="language" />
				</p>

                <h2>Geographic Coverage</h2>
				<xsl:for-each select="coverage/geographicCoverage">
					<p><b>Description: </b> <xsl:value-of select="geographicDescription" /></p>
					<p><b>Coordinates:</b></p>
					<ul>
						<li>West: <xsl:value-of select="boundingCoordinates/westBoundingCoordinate" /></li>
						<li>East: <xsl:value-of select="boundingCoordinates/eastBoundingCoordinate" /></li>
						<li>North: <xsl:value-of select="boundingCoordinates/northBoundingCoordinate" /></li>
						<li>South: <xsl:value-of select="boundingCoordinates/southBoundingCoordinate" /></li>
					</ul>
				</xsl:for-each>

                <h2>Temporal Coverage</h2>
                <p>
                    <b>From: </b> <xsl:value-of select="coverage/temporalCoverage/rangeOfDates/beginDate/calendarDate" /> 
                    <b> To: </b> <xsl:value-of select="coverage/temporalCoverage/rangeOfDates/endDate/calendarDate" />
                </p>

                <h2>Keywords</h2>
                <ul>
                    <xsl:for-each select="keywordSet/keyword">
                        <li><xsl:value-of select="." /></li>
                    </xsl:for-each>
                </ul>

				<h2>Taxonomic Coverage</h2>
				<p><b>General Taxonomic Coverage: </b>
					<xsl:value-of select="coverage/taxonomicCoverage/generalTaxonomicCoverage" />
				</p>
				<xsl:apply-templates select="coverage/taxonomicCoverage/taxonomicClassification" />

				<h2>Maintenance</h2>
				<p><b>Description: </b> 
					<xsl:value-of select="maintenance/description" />
				</p>
				<p><b>Update Frequency: </b> 
					<xsl:value-of select="maintenance/maintenanceUpdateFrequency" />
				</p>

                <h2>Project Personnel</h2>
                <table>
                    <tr>
                        <th>Name</th>
                        <th>Organization</th>
                        <th>Role</th>
                    </tr>
                    <xsl:for-each select="project/personnel">
                        <tr>
                            <td>
                                <xsl:value-of select="individualName/givenName" /> 
								<xsl:text> </xsl:text>
                                <xsl:value-of select="individualName/surName" />
                            </td>
                            <td><xsl:value-of select="organizationName" /></td>
                            <td><xsl:value-of select="role" /></td>
                        </tr>
                    </xsl:for-each>
                </table>

                <h2>Contact Information</h2>
                <p><b>Name: </b> 
                    <xsl:value-of select="contact/individualName/givenName" /> 
					<xsl:text> </xsl:text>
                    <xsl:value-of select="contact/individualName/surName" />
                </p>
                <p><b>Organization: </b> <xsl:value-of select="contact/organizationName" /></p>
                <p><b>Email: </b> <xsl:value-of select="contact/electronicMailAddress" /></p>
                <p><b>Address: </b> 
                    <xsl:value-of select="contact/address/deliveryPoint" />, 
                    <xsl:value-of select="contact/address/city" />, 
                    <xsl:value-of select="contact/address/administrativeArea" />
					<xsl:text> </xsl:text>
                    <xsl:value-of select="contact/address/postalCode" />
                </p>

				<h2>Publisher</h2>
				<p><b>Organization: </b> 
					<xsl:value-of select="publisher/organizationName" />
				</p>
				<p><b>Address: </b> 
					<xsl:value-of select="publisher/address/deliveryPoint" />, 
					<xsl:value-of select="publisher/address/city" />, 
					<xsl:value-of select="publisher/address/administrativeArea" /> 
					<xsl:text> </xsl:text>
					<xsl:value-of select="publisher/address/postalCode" />
				</p>
				<p><b>Email: </b> 
					<xsl:value-of select="publisher/electronicMailAddress" />
				</p>
				<p><b>Website: </b> 
					<a href="{publisher/onlineUrl}">
						<xsl:value-of select="publisher/onlineUrl" />
					</a>
				</p>

                <h2>Methods</h2>
                <xsl:for-each select="methods/methodStep/description/para">
                    <p><xsl:value-of select="normalize-space()" /></p>
                </xsl:for-each>

				<h2>Data Table</h2>
				<p><b>Entity Name: </b> 
					<xsl:value-of select="dataTable/entityName" />
				</p>
				<p><b>Description: </b> 
					<xsl:value-of select="dataTable/entityDescription" />
				</p>

				<h3>Physical Information</h3>
				<p><b>File Name: </b> <xsl:value-of select="dataTable/physical/objectName" /></p>
				<p><b>Size: </b> <xsl:value-of select="dataTable/physical/size" /> bytes</p>
				<p><b>Format: </b></p>
				<ul>
					<li><b>Number of header lines: </b><xsl:value-of select="dataTable/physical/dataFormat/textFormat/numHeaderLines" /></li>
					<li><b>Record delimiter: </b><xsl:value-of select="dataTable/physical/dataFormat/textFormat/recordDelimiter" /></li>
					<li><b>Attribute orientation: </b><xsl:value-of select="dataTable/physical/dataFormat/textFormat/attributeOrientation" /></li>
					<li><b>Field delimiter: </b><xsl:value-of select="dataTable/physical/dataFormat/textFormat/simpleDelimited/fieldDelimiter" /></li>
					<li><b>Quote character: </b><xsl:value-of select="dataTable/physical/dataFormat/textFormat/simpleDelimited/quoteCharacter" /></li>
				</ul>

				<h3>Attributes</h3>
				<table>
					<tr>
						<th>Attribute Name</th>
						<th>Label</th>
						<th>Definition</th>
						<th>Type</th>
					</tr>
					<xsl:for-each select="dataTable/attributeList/attribute">
						<tr>
							<td><xsl:value-of select="attributeName" /></td>
							<td><xsl:value-of select="attributeLabel" /></td>
							<td><xsl:value-of select="attributeDefinition" /></td>
							<td><xsl:value-of select="storageType" /></td>
						</tr>
					</xsl:for-each>
				</table>

				<p><b>Number of Records: </b> 
					<xsl:value-of select="dataTable/numberOfRecords" />
				</p>
				
            </body>
        </html>
    </xsl:template>

	<!-- Uses CSS to indent the Taxonomy section -->
    <xsl:template match="taxonomicClassification">
        <!-- Calculate the level of indentation based on the depth of recursion -->
        <xsl:variable name="level" select="count(ancestor::taxonomicClassification)" />
        <p style="margin-left: {count(ancestor::taxonomicClassification) * 20}px;">
            <b><xsl:value-of select="taxonRankName" />: </b>
            <xsl:value-of select="taxonRankValue" /> (<xsl:value-of select="commonName" />)
        </p>
        <xsl:if test="taxonomicClassification">
            <xsl:apply-templates select="taxonomicClassification"/>
        </xsl:if>
    </xsl:template>

</xsl:stylesheet>
