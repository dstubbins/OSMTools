#---------------------------------------------------------------------------
#This Python script will load osm xml into a file geodatabase
#It works against the compressed *.bz2 file to save space
#resulting fgdb will contain:
# Nodes where they have useful tags.
# Linear ways where they have useful tags
# Area ways where lines are closed loops and have useful tags
# including multipart polygons built from areas where the Relation has useful tags
#Updated to support relations for some multipolygon support
#during the conversion process temporary files are used to reduce memory footprint
#you should be able to load the complete planet without memory issues, however it will take a long time
#Loading continents or countries is more feasible.
#you will need aprox 2x the bz2 files space for temporary space
#also space for output data. The block size controls the ammount of memory it will use
# 4 works on my 1Gb Laptop.  YMMV. small uses less memory but is slower, though not much.
#---------------------------------------------------------------------------
#   Name:       OSM Simple Loader
#   Version:    2.0
#   Authored    By: Dominic Stubbins
#   License:  Apache 2.0.
#---------------------------------------------------------------------------
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


#Import modules
import arcpy, sys, os,fileinput,bz2,math,time
starttime=time.time()

try:
    paramInFile=str(sys.argv[1])        #The OSM Bzfile to load
    paramDestDir=str(sys.argv[2])       #where to create the output fgdb
    paramGDB=str(sys.argv[3])           #Name of output FGDB
    paramBSize=int(sys.argv[4])         #scale much memory to use
    paramScratch=str(sys.argv[5])       #working area - needs to be at 2x size of BZ file

except Exception, ErrorDesc:
    arcpy.AddError("Input parameters are incorrect")

#standard fields to poulate in Tags (replace ":" with "_" e.g. addr:city  becomes addr_city

standardFields = set(('highway','name','name_en','ref','lanes','surface','oneway','maxspeed','tracktype','access','service','foot','bicycle','bridge','barrier','lit','layer',
                      'building','building_levels','building_height','addr_housenumber','addr_street','addr_city','addr_postcode','addr_country','addr_place','addr_state',
                      'natural','landuse','waterway','power','amenity','place','height','note','railway','public_transport','operator','guage','width','tunnel',
                    'leisure','is_in','ele','shop','man_made','parking',
                    'boundary','aerialway','aeroway','craft','emergency','geological','historic','military','office',
                    'sport','tourism','traffic_calming','entrance','crossing'))

#Tags with these keys will not be loaded, features with *only* these keys will not be loaded
ignoreFields = set(('created_by','source','converted_by'))

#this flag controls whether features with only non standard tags are loaded.
loadNonstandardTags=False

#Are we actually gong to load the features into the fgdb or just test processing
commitareas=True
commitlines=True
commitnodes=True



sourcefile=paramInFile
output=paramDestDir+"\\" + paramGDB
nodefc=output + "\\nodes"
nodeothertag=output + "\other_node_tags"
wayothertag=output+"\other_way_tags"
wayfc=output + "\osm_ways"
finalwayfc=output + "\ways"
areawayfc=output + "\osm_area_ways"
finalareawayfc=output + "\\area_ways"
waytagtab=output+"\osm_way_tags"
temproadsfc=output+"\loopyroads"
coordsys='Coordinate Systems\Geographic Coordinate Systems\World\WGS 1984.prj'
scratchSpace=paramScratch




#how many nodes to load into memory for building ways, adjust according to memory
blocksize=paramBSize * 500000

nodecount=0
relcount=0
membercount=0
taggednodecount=0
segmentcount=0
waycount=0
nodetagcount=0
waytagcount=0
ftype=-1
hasvalidtags=False

stepstarttime=time.time()
#prepare target featureclasses
arcpy.AddMessage('Step 1/5')
arcpy.AddMessage("preparing target feature Classes")

arcpy.toolbox = "management"
if not arcpy.Exists(output):
    outWorkspace=arcpy.CreateFileGDB_management(os.path.split(output)[0], os.path.split(output)[1])

if not arcpy.Exists(nodefc):
    arcpy.CreateFeatureclass_management(output, "nodes", "point", "#", "DISABLED", "DISABLED", coordsys)
    arcpy.AddField_management(nodefc, "Node_ID", "TEXT","30","#","30")
    for fieldname in standardFields:
        arcpy.AddField_management(nodefc,fieldname,"TEXT","#","#","255")

if not arcpy.Exists(nodeothertag):
    arcpy.CreateTable_management(output, "other_node_tags")
    arcpy.AddField_management(nodeothertag,"Node_ID","TEXT","30","#","30")
    arcpy.AddField_management(nodeothertag,"Tag_Name","TEXT","30","#","30")
    arcpy.AddField_management(nodeothertag,"Tag_Value","TEXT","255","#","255")

if not arcpy.Exists(wayfc):
    arcpy.CreateFeatureclass_management(output, "osm_ways", "polyline", "#", "DISABLED", "DISABLED",coordsys)
    arcpy.AddField_management(wayfc, "Way_ID", "TEXT","30","#","30")


if not arcpy.Exists(areawayfc):
    arcpy.CreateFeatureclass_management(output, "osm_area_ways", "polygon", "#", "DISABLED", "DISABLED",coordsys)
    arcpy.AddField_management(areawayfc, "Way_ID", "TEXT","30","#","30")
    #arcpy.RemoveSpatialIndex_management(areawayfc)


if not arcpy.Exists(wayothertag):
    arcpy.CreateTable_management(output, "other_way_tags")
    arcpy.AddField_management(wayothertag,"Way_ID","TEXT","30","#","30")
    arcpy.AddField_management(wayothertag,"Tag_Name","TEXT","#","#","30")
    arcpy.AddField_management(wayothertag,"Tag_Value","TEXT","#","#","255")

if not arcpy.Exists(waytagtab):
    arcpy.CreateTable_management(output, "osm_way_tags")
    arcpy.AddField_management(waytagtab,"Way_ID","TEXT","30","#","30")
    for fieldname in standardFields:
        arcpy.AddField_management(waytagtab,fieldname,"TEXT","#","#","255")


#create a dictionary of fields to use when writing to the feature classes and tables
nodefieldlookup={}
nodefieldlist=[]
nodefieldvalues=[]
nodefieldlookup["Node_ID"]=0
nodefieldlist.append("Node_ID")
nodefieldvalues.append('')
nodefieldlookup["SHAPE@XY"]=1
nodefieldlist.append("SHAPE@XY")
nodefieldvalues.append((0,0))
pos=2
for fieldname in standardFields:
    nodefieldlookup[fieldname]=pos
    nodefieldlist.append(fieldname)
    nodefieldvalues.append('')
    pos=pos+1
nodefieldcount=len(nodefieldvalues)


wayfieldlookup={}
wayfieldlist=[]
wayfieldvalues=[]
wayfieldlookup["Way_ID"]=0
wayfieldlist.append("Way_ID")
wayfieldvalues.append('')
pos=1
for fieldname in standardFields:
    wayfieldlookup[fieldname]=pos
    wayfieldlist.append(fieldname)
    wayfieldvalues.append('')
    pos=pos+1
wayfieldcount= len(wayfieldvalues)



inputfile=bz2.BZ2File(sourcefile,'r')

#---------------------------------------------------------------------------
#Gets the XML element name from the string passed in
#an end of element tag is /element
#---------------------------------------------------------------------------
def getElement(line):
    s=line.find('<')
    e=line.find(' ',s)
    el=line[s+1:e]
    if el[0:1]=='/':
        el=el[0:len(el)-1]
    return el
#---------------------------------------------------------------------------


#---------------------------------------------------------------------------
#Gets the value of the named attribute from the string
#---------------------------------------------------------------------------
def getAttributeValue(name,line):
    sa=line.find(' '+name+'="')+len(name)+3
    #ea=line.find('"',sa)
    #attr=line[sa:ea]

    return line[sa:line.find('"',sa)]
#---------------------------------------------------------------------------

#---------------------------------------------------------------------------
#Extract Node attribute details from a line of xml text
#---------------------------------------------------------------------------
def returnNode(line):
    nid=getAttributeValue('id',line)
    nx=getAttributeValue('lon',line)
    ny=getAttributeValue('lat',line)

    return(nid,nx,ny)
#---------------------------------------------------------------------------


#get the id attribute from a line of xml text
#used for ways and its segs, as id is only attribute needed
def returnID(line):

    return getAttributeValue('id',line)
#-----------------------------------------------------------------------------------


#This function creates ways by searching blobks of node id's loaded into memory
#works its way through the unbuilt ways, swapping nodeid's for node coordinates as it finds them
#when it has iterated all the node blocks it should be done

def buildWays(scratch,blocks):
    nodes={}
    #areawaycursor=arcpy.da.InsertCursor(areawayfc,("way_id","SHAPE@"))
    completedways = 0
    counter=0
    #completed features are writen here
    builtareas=bz2.BZ2File(scratch+'/builtareas.dat','w')
    builtlines=bz2.BZ2File(scratch+'/builtlines.dat','w')
    #loop through each block of nodes loaded from file
    for fs in range(1,blocks+1):
        nodefile=bz2.BZ2File(scratch+'/nodeblock'+str(fs)+'.dat','r')
        arcpy.AddMessage('Loading Block ' +str(fs))

        #add nodes to a dictionary
        for node in nodefile:
            snode=node.rstrip('\n').split(':')
            nodes[snode[0]]=(snode[1],snode[2])
        nodefile.close()
        arcpy.AddMessage('Searching Block ' +str(fs))
        unbuiltways=bz2.BZ2File(scratch+'/unbuiltways.dat','r')
        stillunbuiltways=bz2.BZ2File(scratch+'/stillunbuiltways.dat','w')
        for way in unbuiltways:
            wayitems=way.rstrip('\n').rstrip(':').split('#')
            if len(wayitems) ==2:
                wayid=wayitems[0]
                waynodes=wayitems[1].split(':')
                wayout=str(wayid)+'#'
                isAllComplete=True
                for anode in waynodes:
                    if ' ' in anode:
                        wayout=wayout+anode+':'
                    elif anode in nodes:
                        thenode=nodes[anode]
                        wayout=wayout+thenode[0]+' '+thenode[1]+':'
                    else:
                        isAllComplete=False
                        wayout=wayout+anode+':'
                #if a way is complete write it to a seperate file, if not write for next loop
                if isAllComplete:
                    finalnodes=wayout.split('#')[1].split(':')
                    completedways +=1
                    if finalnodes[0] <> finalnodes[-2]:     #start point is different to end point so its a line
                        builtlines.write(wayout+'\n')
                    else:
                        builtareas.write(wayout+'\n')       #its an area
                else:
                    stillunbuiltways.write(wayout+'\n')
        arcpy.AddMessage("Processed Ways="+str(completedways))
        nodes.clear()
        unbuiltways.close()
        stillunbuiltways.close()
        os.remove(scratch+'/unbuiltways.dat')
        os.rename(scratch+'/stillunbuiltways.dat',scratch+'/unbuiltways.dat')
    builtareas.close()
    builtlines.close()
    return completedways

##--------------------------------------------------------------------------------------



arcpy.AddMessage("Step 1 --- %s seconds ---" % (time.time() - stepstarttime))
stepstarttime=time.time()
unbuiltways=bz2.BZ2File(scratchSpace+'/unbuiltways.dat','w')
unbuiltrelations=bz2.BZ2File(scratchSpace+'/unbuiltrelations.dat','w')

arcpy.AddMessage('Step 2/5')
arcpy.AddMessage('Loading Nodes & Tags')
node=('ID','x','y')
segment=('id','start','end')
way=('id','seg1 seg2')
tag=('key','value')


##------------------------------------------------------------------------------
##First pass through source file
##sort nodes into blocks and write to files
##seperate ways and write to unbuilt ways files
##load tagged nodes into fgdb
##load node and way tags into fgdb
##--------------------------------------------------------------------------------





edit = arcpy.da.Editor(output)
edit.startEditing(False,False)

nodecursor=arcpy.da.InsertCursor(nodefc,nodefieldlist)
waytagcursor=arcpy.da.InsertCursor(waytagtab,wayfieldlist)

if loadNonstandardTags:
    othernodetagcursor=arcpy.da.InsertCursor(nodeothertag,("Node_ID","Tag_Name","Tag_Value"))
    otherwaytagcursor=arcpy.da.InsertCursor(wayothertag,("Way_ID","Tag_Name","Tag_Value"))

nodepnt=arcpy.CreateObject("point")
ftags=[]
waystring=''
linecount=0
blocknum=1
nodefile=bz2.BZ2File(scratchSpace+'/nodeblock'+str(blocknum)+'.dat','w')
switchval=blocksize*blocknum

for uline in inputfile:
    #source should be in utf-8, but sometimes its not.
    line=unicode(uline,"utf-8","replace")
    element=getElement(line)
    linecount+=1
    if element=='node':
        ftags=[]
        node=returnNode(line)
        ftype=0
        if nodecount>switchval:
            nodefile.close()
            blocknum+=1
            switchval=blocknum*blocksize
            nodefile=bz2.BZ2File(scratchSpace+'/nodeblock'+str(blocknum)+'.dat','w')
        #nodefile.write(str(node[0])+':'+str(node[1])+':'+str(node[2])+'\n')
        nodefile.write("%s:%s:%s\n" % node)
        nodecount+=1

    elif element=='way':
        ftags=[]
        ftype=2
        waycount+=1
        way=(returnID(line),'')
        waystring='\n'+str(way[0])+'#'

    elif element=='relation':
        ftags=[]
        ftype=3
        isMultipolygon=False
        rel=(returnID(line),'')
        relstring='\n'+str(rel[0])+'#'

    elif element=='nd':
        waystring=waystring+str(getAttributeValue('ref',line))+':'
        #waystring=('%s%s:') % (waystring,getAttributeValue('ref',line))
    elif element=='member':
        membercount+=1
        relstring=relstring+str(getAttributeValue('ref',line))+':'

    elif element=='tag':
        if ftype==0:
            #tagged node
            tag=(getAttributeValue('k',line).lstrip()[:29].replace(':','_',1),getAttributeValue('v',line)[:254])
            #tag=returnTags(line)
            #ignore less useful tags, and if not a standard tag
            #remove tags with blank values too. lots of wierd keys have blank values

            if tag[0] in standardFields and tag[1] !='':
                #ftags.append((tag[0],tag[1]))
                ftags.append(tag)
                hasvalidtags=True
                nodetagcount+=1
            elif loadNonstandardTags:
                if tag[0] not in ignoreFields and tag[0] not in standardFields and tag[1] !='':
                    hasvalidtags=True
                    othernodetagcursor.insertRow((node[0],tag[0],tag[1]))
                    nodetagcount+=1


        elif ftype==2:
            #way tags, loading all these except ignorefields and blank valued ones.
            #tag=returnTags(line)
            tag=(getAttributeValue('k',line).lstrip()[:29].replace(':','_',1),getAttributeValue('v',line)[:254])
            if tag[0] in standardFields and tag[1] !='':
                ftags.append(tag)
                hasvalidtags=True
                waytagcount+=1
            elif loadNonstandardTags:
                if tag[0] not in ignoreFields and tag[0] not in standardFields and tag[1] !='':
                    otherwaytagcursor.insertRow((way[0],tag[0],tag[1]))
                    waytagcount+=1

        elif ftype==3:
            #relation tags, loading all these except ignorefields and blank valued ones.
            #tag=returnTags(line)
            tag=(getAttributeValue('k',line).lstrip()[:29].replace(':','_',1),getAttributeValue('v',line)[:254])
            if tag[0]=='type' and tag[1]=='multipolygon':
                isMultipolygon=True
            if tag[0] in standardFields and tag[1] !='':
                ftags.append(tag)
                hasvalidtags=True
                waytagcount+=1
            elif loadNonstandardTags:
                if tag[0] not in ignoreFields and tag[0] not in standardFields and tag[1] !='':
                    otherwaytagcursor.insertRow((way[0],tag[0],tag[1]))
                    waytagcount+=1




    elif hasvalidtags and ftype==0 and element=='/node':
        nodefieldvalues[0]=node[0]
        nodefieldvalues[1]=((float(node[1]),float(node[2])))
        #nodefieldvalues[1]=((node[1]),(node[2]))
        for sTag in ftags:
            nodefieldvalues[nodefieldlookup[sTag[0]]]=sTag[1]
        if commitnodes:
            nodecursor.insertRow(nodefieldvalues)
        nodefieldvalues[0]=''
        nodefieldvalues[1]=''
        for sTag in ftags:
            nodefieldvalues[nodefieldlookup[sTag[0]]]=''
        taggednodecount+=1
        hasvalidtags=False




    elif element=='/way':#hasvalidtags and element=='/way': - not checking tags because blank ways are often part of relations so removed by inner join in step7
        #done with way lets load attributes, shape comes later
        unbuiltways.write(waystring)
        if len(ftags)>0:
            wayfieldvalues[0]=way[0]
            for sTag in ftags:
                wayfieldvalues[wayfieldlookup[sTag[0]]]=sTag[1]
            if commitareas and commitlines:
                waytagcursor.insertRow(wayfieldvalues)
            nodefieldvalues[0]=''
            for sTag in ftags:
                wayfieldvalues[wayfieldlookup[sTag[0]]]=''
        hasvalidtags=False

    elif hasvalidtags and element=='/relation':
        #done with relation lets load attributes, shape comes later
        if isMultipolygon:
            relcount+=1
            unbuiltrelations.write(relstring)
            if len(ftags)>0:
                wayfieldvalues[0]=rel[0]
                for sTag in ftags:
                    wayfieldvalues[wayfieldlookup[sTag[0]]]=sTag[1]
                if commitareas and commitlines:
                    waytagcursor.insertRow(wayfieldvalues)
                nodefieldvalues[0]=''
                for sTag in ftags:
                    wayfieldvalues[wayfieldlookup[sTag[0]]]=''
        hasvalidtags=False



    if linecount==5000000:
        linecount=0
        arcpy.AddMessage(str(nodecount) +' Vertices   '+str(relcount)+' relations     '+str(waycount)+' Ways     ' + str(taggednodecount) +' Tagged Nodes     '+str(nodetagcount)+ ' Node Tags')
        #commit to gdb whats been done
        edit.stopEditing(True)
        edit.startEditing(False,False)



edit.stopEditing(True)
#Close files that were written to.
nodefile.close()
unbuiltways.close()
unbuiltrelations.close()
arcpy.AddMessage( str(nodecount) +' Vertices   ' +str(taggednodecount)+'  Nodes    '+str(waycount)+' Ways ' +str(relcount)+' relations '+str(membercount)+' members ')
arcpy.AddMessage("Step 2 --- %s seconds ---" % (time.time() - stepstarttime))


###phase 3 process ways
stepstarttime=time.time()
arcpy.AddMessage('Step 3/5')
arcpy.AddMessage('Assembling Ways from nodes')
completedways = buildWays(scratchSpace,blocknum)
arcpy.AddMessage("Total Ways Processed="+str(completedways))
arcpy.AddMessage("Step 3 --- %s seconds ---" % (time.time() - stepstarttime))


#Step 4
#Load the linear ways built in step 3
stepstarttime=time.time()
arcpy.AddMessage("Step 4 Loading Lines")
completedways=0
builtlines=bz2.BZ2File(scratchSpace+'/builtlines.dat','r')
linewaycursor=arcpy.da.InsertCursor(wayfc,("way_id","SHAPE@"))
for lineway in builtlines:
    linewayitems=lineway.rstrip('\n').rstrip(':').split('#')
    if len(linewayitems) ==2:
        linewayid=linewayitems[0]
        linewaynodes=linewayitems[1].split(':')
        shape=[]
        for waypoints in linewaynodes:
            partcoords=waypoints.split(' ')
            if len(partcoords)==2:
                shape.append((partcoords[0],partcoords[1]))
        row=(linewayid,shape)
        try:
            if commitlines:
                linewaycursor.insertRow(row)
                completedways +=1
        except Exception, ErrorDesc:
            arcpy.AddMessage("Failed to load as line wayid="+str(linewayid))
builtlines.close()
del linewaycursor
arcpy.AddMessage("Loaded Lines="+str(completedways))
arcpy.AddMessage("Step 4 --- %s seconds ---" % (time.time() - stepstarttime))




#Step 5
#load the area ways built in step 3
stepstarttime=time.time()
arcpy.AddMessage("Step 5 Loading Areas")
completedways =0
builtareas=bz2.BZ2File(scratchSpace+'/builtareas.dat','r')
areawaycursor=arcpy.da.InsertCursor(areawayfc,("way_id","SHAPE@"))
#waycursor=arcpy.da.InsertCursor(wayfc,("way_id","SHAPE@"))
for areaway in builtareas:
    areawayitems=areaway.rstrip('\n').rstrip(':').split('#')
    if len(areawayitems) ==2:
        areawayid=areawayitems[0]
        areawaynodes=areawayitems[1].split(':')
        shape=[]
        for waypoints in areawaynodes:
            partcoords=waypoints.split(' ')
            if len(partcoords)==2:
                shape.append((partcoords[0],partcoords[1]))
        row=(areawayid,shape)
        #arcpy.AddMessage(str(row))
        try:
            if commitareas:
                areawaycursor.insertRow(row)
                completedways +=1
        except Exception, ErrorDesc:
            arcpy.AddMessage("Failed to load as area wayid="+str(areawayid))
builtareas.close()
del areawaycursor
arcpy.AddMessage("Loaded Areas="+str(completedways))
arcpy.AddMessage("Step 5 --- %s seconds ---" % (time.time() - stepstarttime))

#Step 6 Create Indexes
stepstarttime=time.time()
arcpy.AddMessage('Step 6/7')
arcpy.AddMessage('Building Indexes')

try:
    arcpy.AddSpatialIndex_management(nodefc,0.5)
    arcpy.AddIndex_management(waytagtab,"Way_ID","Way_Idx","UNIQUE","#")
    arcpy.AddIndex_management(wayfc,"Way_ID","Way_Idx","UNIQUE","#")
    arcpy.AddIndex_management(areawayfc,"Way_ID","Way_Idx","UNIQUE","#")
    arcpy.AddIndex_management(nodeothertag,"Node_ID","Node_Idx","NON_UNIQUE","#")
    arcpy.AddIndex_management(wayothertag,"Way_ID","Way_Idx","NON_UNIQUE","#")
    arcpy.AddMessage("Step 6 --- %s seconds ---" % (time.time() - stepstarttime))
except Exception, ErrorDesc:
    arcpy.AddMessage("Failed to build index")


#Step Relations.....
#create multipolygon relations by searching through the area ways for the referenced parts.
#only load those made from areas, if made from lines they are not found.
#Only if the relation has valid tags on the parent relation will it be in the list
arcpy.AddMessage('Step 6.5/7')
arcpy.AddMessage('Building Multipolygons')
stepstarttime=time.time()
unbuiltrelations=bz2.BZ2File(scratchSpace+'/unbuiltrelations.dat','r')
edit = arcpy.da.Editor(output)
edit.startEditing(False,False)
areawaycursor=arcpy.da.InsertCursor(areawayfc,("way_id","SHAPE@"))
completerels=0
relcount=0
SR = arcpy.Describe(areawayfc).spatialReference
shape=arcpy.Array()
for rel in unbuiltrelations:
    relcount+=1
    if relcount==500:
        relcount=0
        arcpy.AddMessage('Multipolygons='+str(completerels))
    areawayitems=rel.rstrip('\n').rstrip(':').split('#')
    if len(areawayitems)==2:
        shape.removeAll()
        relid=areawayitems[0]
        members=areawayitems[1].split(':')
        queryexpression=""""way_id" in ("""
        expecteditems=len(members)
        for member in members:
            queryexpression=queryexpression+"'"+str(member)+"',"
        queryexpression=queryexpression.rstrip(',')+')'
        actualitems=0
        for row in arcpy.da.SearchCursor(areawayfc,("way_id","SHAPE@"),queryexpression):
            for part in row[1]:
                shape.add(part)
            actualitems+=1
        if actualitems==expecteditems:
            inShape=arcpy.Polygon(shape,SR)
            newrow=(relid,inShape)
            try:
                if commitareas:
                    areawaycursor.insertRow(newrow)
                    completerels +=1
            except Exception, ErrorDesc:
                arcpy.AddMessage("Failed to load as area wayid="+str(relid)+ " "+str(ErrorDesc))
edit.stopEditing(True)
unbuiltrelations.close()
del areawaycursor
arcpy.AddMessage("Complete multiAreas="+str(completerels))
arcpy.AddMessage("Step 6.5 --- %s seconds ---" % (time.time() - stepstarttime))





#Step 7 join Attributes to ways
stepstarttime=time.time()
arcpy.AddMessage('Step 7/7')
arcpy.AddMessage("joining attributes to way features")
arcpy.MakeFeatureLayer_management(wayfc, "tempway", "", "", "Shape_Length Shape_Length VISIBLE;Way_ID Way_ID VISIBLE")
arcpy.AddJoin_management("tempway", "Way_ID", waytagtab, "Way_ID", "KEEP_COMMON")
arcpy.CopyFeatures_management("tempway", finalwayfc, "", "0.05", "0.5", "5.0")
arcpy.Delete_management("tempway")
arcpy.Delete_management(wayfc)
arcpy.AddMessage("joining attributes to area features")
arcpy.MakeFeatureLayer_management(areawayfc, "temparea", "", "", "Shape_Length Shape_Length VISIBLE;Way_ID Way_ID VISIBLE")
arcpy.AddJoin_management("temparea", "Way_ID", waytagtab, "Way_ID", "KEEP_COMMON")
arcpy.CopyFeatures_management("temparea", finalareawayfc, "", "0.05", "0.5", "5.0")
arcpy.Delete_management("temparea")
arcpy.Delete_management(areawayfc)
arcpy.Delete_management(waytagtab)

#Sort out some of the mess caused by loading all loops as areas.

#copy highways that are loops from areas to line feature class needs an ArcInfo License
if arcpy.CheckProduct("ArcInfo") == "Available":
    arcpy.AddMessage("Tidying areas that should be lines")
    arcpy.MakeFeatureLayer_management(finalareawayfc,"loopyroads","osm_way_tags_highway <> ''")
    arcpy.FeatureToLine_management( "loopyroads",temproadsfc)
    arcpy.Append_management(temproadsfc,finalwayfc,"NO_TEST")
    arcpy.Delete_management(temproadsfc)


arcpy.AddMessage("Step 7 --- %s seconds ---" % (time.time() - stepstarttime))

#Completed
arcpy.AddMessage("Conversion Completed")
arcpy.AddMessage(str(nodecount) +' Nodes    '+str(waycount)+' Ways'+str(relcount)+' relations     ')
arcpy.AddMessage("Total runtime  --- %s seconds ---" % (time.time() - starttime))
