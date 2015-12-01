title: OpenStreetMap Loader
Version: 2.0
Author: Dominic Stubbins
Date: Dec 2015
license: Apache 2.0


##Copyright 2015 Dominic Stubbins
##
##Licensed under the Apache License, Version 2.0 (the "License");
##you may not use this file except in compliance with the License.
##You may obtain a copy of the License at
##
##    http://www.apache.org/licenses/LICENSE-2.0
##
##Unless required by applicable law or agreed to in writing, software
##distributed under the License is distributed on an "AS IS" BASIS,
##WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
##See the License for the specific language governing permissions and
##limitations under the License.






This direcotry contains an ArcGIS Toolbox and associated python script for loading the OpenStreetMap BZ compressed xml file into an ArcGIS File Based Geodatabase.  To use this tool you will need to have a copy of ArcGIS Desktop installed.

Installation:
UNzip OSMLoader.zip into a directory.
In ArcCatalog or ArcMap Toolbox pane "Add New Toolbox"  Browse to OSMTools.tbx.
The toolbox contains a script tool called OSM_Simple_Loader.


Usage:
Run the tool by double clicking the Icon within ArcGIS toolbox view.
If you have only a single core machine, you may find a significant performance benefit by running the tool from the dos cmd line, as this will save you the arccatalog overhead.  With enough memory it is better to run using a 64bit version of python and arcpy.

Known Issues:
some linear features that are loops are loaded into the areas feature class
Multipolygon relations are only supported where each part is an area and the attributes are on the parent

