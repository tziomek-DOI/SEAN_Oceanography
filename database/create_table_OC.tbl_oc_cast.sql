
/****** Object:  Table [OC].[tbl_oc_cast]    Script Date: 3/22/2024 1:25:21 PM 
 * 
 * We need at least one more extra character for field 'cast'. Change from 2 to 4, which should be more than enough.
 *
 ******/

/*
 * !!!! Do not DROP THE TABLE like this.
 * First rename the existing table, then run this as a CREATE script, then SSIS the data over, then the old version can be removed.
 *
IF  EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[OC].[tbl_oc_cast]') AND type in (N'U'))
DROP TABLE [OC].[tbl_oc_cast]
GO
*/

/****** Object:  Table [OC].[tbl_oc_cast]    Script Date: 3/22/2024 1:25:21 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [OC].[tbl_oc_cast](
	[ctd] [varchar](1) NOT NULL,
	[dump] [varchar](4) NOT NULL,
	[cast] [varchar](4) NOT NULL,
	[station] [varchar](2) NOT NULL,
	[latitude] [real] NULL,
	[longitude] [real] NULL,
	[date_gmt] [datetime] NULL,
	[time_gmt] [datetime] NULL,
	[fathometer_depth] [int] NULL,
	[depth] [int] NOT NULL,
	[pressure] [real] NULL,
	[temperature] [real] NULL,
	[conductivity] [real] NULL,
	[salinity] [real] NULL,
	[sigma_t] [real] NULL,
	[fluorescence] [real] NULL,
	[obs] [real] NULL,
	[oxygen] [real] NULL,
	[par] [real] NULL,
	[data_quality] [varchar](1) NULL,
	[data_quality_comment] [varchar](512) NULL,
	[time_stamp] [datetime] NOT NULL,
	[protocol_id] [varchar](10) NOT NULL,
	[userid] [varchar](20) NOT NULL,
	[submission_number] [int] NOT NULL,
	[vessel] [varchar](24) NULL,
	[sbe_data_flag] [real] NULL,
	[comments] [varchar](512) NULL,
	[observer] [varchar](50) NULL,
	[target_depth] [int] NULL,
	[cruise_year] [varchar](4) NULL,
	[id] [int] NOT NULL
) ON [PRIMARY]
GO


