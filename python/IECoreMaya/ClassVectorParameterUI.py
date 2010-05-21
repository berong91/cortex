##########################################################################
#
#  Copyright (c) 2010, Image Engine Design Inc. All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#
#     * Neither the name of Image Engine Design nor the names of any
#       other contributors to this software may be used to endorse or
#       promote products derived from this software without specific prior
#       written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
#  IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
#  CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
#  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
#  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
##########################################################################

from __future__ import with_statement

import maya.cmds

import IECore
import IECoreMaya

## A ParameterUI for ClassVectorParameters. Supports the following Parameter userData entries :
#
#   BoolData ["UI"]["collapsable"]
#     Specifies if the UI may be collapsed or not - defaults to True. 
#
# The icon used for a child UI can be overridden by setting the icon name, minus extension in either
# the child classes blindData, or its top level compound parameters userData() as follows:
# 
#   StringData <class.blindData()|class.parameters().userData()>["UI"]["icon"]
# 
# If a parameter of a class has one of the following userData elements set to True, a minimal version
# of the control for that parameter will be placed in the header row for the class entry,
# either before, or after the icon/name.
# 
#   BoolData ["UI"]["classVectorParameterPreHeader"]
#   BoolData ["UI"]["classVectorParameterHeader"]
#
# \TODO See if there is a better way to deal with problematic UI elements (eg: spline) that crash
# when a redraw is called and constituent plugs no longer exist. This can happen when removing
# classes, or changing parameter types, as an AE redraw may happen before the related UI
# has been deleted. It seems for some parameter types, maya doesn't check to see if all 
# the required plugs are there during a redraw, and consequently falls over.
# This behavior is currently compensated for by pre-updating the UI before removing a class
# or changing its version.
class ClassVectorParameterUI( IECoreMaya.ParameterUI ) :

	def __init__( self, node, parameter, **kw ) :
		
		# we have to get the collapse state right at the point we create the frameLayout
		# otherwise maya doesn't get the frame sizing right. we can then specify the rest
		# of the frame state after calling the base class constructor.			
		collapsable = True
		with IECore.IgnoredExceptions( KeyError ) :
			collapsable = parameter.userData()["UI"]["collapsable"].value

		IECoreMaya.ParameterUI.__init__(
			
			self,
			node,
			parameter,
			maya.cmds.frameLayout( collapsable=collapsable, manage=False ),
			**kw
			
		)
				
		self.__kw = kw.copy()
		if collapsable :
			self.__kw["hierarchyDepth"] = self.__kw.get( "hierarchyDepth", -1 ) + 1
		
		maya.cmds.frameLayout(
		
			self._topLevelUI(),
			edit = True,
			label = self.label(),
			labelIndent = IECoreMaya.CompoundParameterUI._labelIndent( self.__kw["hierarchyDepth"] ),
			labelVisible = collapsable,
			font = IECoreMaya.CompoundParameterUI._labelFont( self.__kw["hierarchyDepth"] ),
			borderVisible = False,
			collapsable = collapsable,
			collapse = collapsable,
			manage = True,
				
		)
					
		self.__formLayout = maya.cmds.formLayout( parent=self._topLevelUI() )
	
		self.__addButton = maya.cmds.picture( image="setEdAddCmd.xpm", parent=self.__formLayout )
		IECoreMaya.createMenu( IECore.curry( self.__classMenuDefinition, None ), self.__addButton )
		IECoreMaya.createMenu( IECore.curry( self.__classMenuDefinition, None ), self.__addButton, button=1 )
			
		self.__classInfo = []
		self.__childUIs = {} # mapping from parameter name to ui name
		
		self.replace( node, parameter )
			
	def replace( self, node, parameter ) :
		
		nodeChanged = self.node() != node
				
		IECoreMaya.ParameterUI.replace( self, node, parameter )

		self.__updateChildUIs( startFromScratch=nodeChanged )

	def __classMenuDefinition( self, parameterName ) :
	
		result = IECore.MenuDefinition()
		
		classNameFilter = "*"
		try :
			classNameFilter = self.parameter.userData()["UI"]["classNameFilter"].value
		except :
			pass
		menuPathStart = max( 0, classNameFilter.find( "*" ) )
			
		loader = IECore.ClassLoader.defaultLoader( self.parameter.searchPathEnvVar() )
		for className in loader.classNames( classNameFilter ) :
			classVersions = loader.versions( className )
			for classVersion in classVersions :
				
				active = True
				if parameterName :
					active = self.parameter.getClass( parameterName, True )[1:] != ( className, classVersion )
				
				menuPath = "/" + className[menuPathStart:]
				if len( classVersions ) > 1 :
					menuPath += "/v" + str( classVersion )

				result.append(
					
					menuPath, 
					
					IECore.MenuItemDefinition(
						command = IECore.curry( self._setClass, parameterName, className, classVersion ),
						active = active
					)
					
				)
	
		return result
			
	def _removeClass( self, parameterName ) :
	
		fnPH = IECoreMaya.FnParameterisedHolder( self.node() )
		
		classes = [ c[1:] for c in self.parameter.getClasses( True ) if c[1] != parameterName ]
		
		# We have to do a pre-update here, to make sure we delete the UI for any classes we
		# are going to remove, before we remove them in C++. See the notes at the top.
		self.__updateChildUIs( classes )
		
		fnPH.setClassVectorParameterClasses( self.parameter, classes )
	
	def _setClass( self, parameterName, className, classVersion ) :
	
		fnPH = IECoreMaya.FnParameterisedHolder( self.node() )
		
		# We have to remove this class from the UI first, or, if the parameter list changes,
		# maya can crash as it tries to redraw the AE. See the notes at the top.
		classesWithoutThis = [ c[1:] for c in self.parameter.getClasses( True ) if c[1] != parameterName ]
		self.__updateChildUIs( classesWithoutThis )
		
		classes = [ c[1:] for c in self.parameter.getClasses( True ) ]
		if parameterName :
			foundParameter = False
			for i in range( 0, len( classes ) ) :
				if classes[i][0]==parameterName :
					foundParameter = True
					break
			if not foundParameter :
				raise RuntimeError( "Parameter \"%s\" not present" % parameterName )
			classes[i] = ( parameterName, className, classVersion )
		else :
			# no parameter name - add a new parameter
			parameterNames = set( [ c[0] for c in classes ] )
			for i in range( 0, len( classes ) + 1 ) :
				parameterName = "p%d" % i
				if parameterName not in parameterNames :
					break
		
			classes.append( ( parameterName, className, classVersion ) )
		
		fnPH.setClassVectorParameterClasses( self.parameter, classes )
	
	# \param classes A sequence type based on the list comprehension:
	#     [ c[1:] for c in self.parameter.getClasses(True) ]
	# This is for compatability with fnPH.setClassVectorParameterClasses()
	# which doesn't take the first item of each entry.
	#
	# \param startFromScratch If this is true, then all child uis are
	# removed and rebuilt.
	## \todo If we could reuse child uis (because they had a replace() method)
	# then we wouldn't need the startFromScratch argument.
	def __updateChildUIs( self, classes=None, startFromScratch=False ) :
		
		if classes == None:	
			classes = [ c[1:] for c in self.parameter.getClasses( True ) ]
		
		# delete any uis for parameters which have disappeared
		
		parameterNamesSet = set( [ c[0] for c in classes ] )
		for parameterName in self.__childUIs.keys() :
			if parameterName not in parameterNamesSet or startFromScratch :
				maya.cmds.deleteUI( self.__childUIs[parameterName]._topLevelUI() )
				del self.__childUIs[parameterName]
		
		# and create or reorder uis for remaining parameters
	
		attachForm = [
			( self.__addButton, "left", 20 + IECoreMaya.CompoundParameterUI._labelIndent( self.__kw["hierarchyDepth"] + 1 ) ),
			( self.__addButton, "bottom", 5 ),
		]
		attachControl = []
		attachNone = []
		prevChildUI = None
		for i in range( 0, len( classes ) ) :
		
			parameterName = classes[i][0]
			
			childUI = self.__childUIs.get( parameterName, None )
			if childUI :
				# delete it if it's not the right sort any more
				if childUI.__className!=classes[i][1] or childUI.__classVersion!=classes[i][2] :
					maya.cmds.deleteUI( childUI._topLevelUI() )
					childUI = None
			
			if not childUI :
				with IECoreMaya.UITemplate( "attributeEditorTemplate" ) :
					maya.cmds.setParent( self.__formLayout )
					childUI = ChildUI( self.parameter[parameterName], **self.__kw )
					childUI.__className = classes[i][1]
					childUI.__classVersion = classes[i][2]
					self.__childUIs[parameterName] = childUI
						
			attachForm += [ 
				( childUI._topLevelUI(), "left", 0 ),
				( childUI._topLevelUI(), "right", 0 ),
			]
			
			if i==0 :
				attachForm.append( ( childUI._topLevelUI(), "top", 5 ) )
			else :
				attachControl.append( ( childUI._topLevelUI(), "top", 0, prevChildUI._topLevelUI() ) )
			
			attachNone.append( ( childUI._topLevelUI(), "bottom" ) )
									
			prevChildUI = childUI

		if prevChildUI :
			attachControl.append( ( self.__addButton, "top", 5, prevChildUI._topLevelUI() ) )
		else :
			attachForm.append( ( self.__addButton, "top", 5 ) )
			
		maya.cmds.formLayout(
			self.__formLayout,
			edit=True,
			attachForm = attachForm,
			attachControl = attachControl,
			attachNone = attachNone
		)
	
	@staticmethod
	def _classesSetCallback( fnPH, parameter ) :
			
		for instance in IECoreMaya.UIElement.instances( ClassVectorParameterUI ) :
			if instance.parameter.isSame( parameter ) :
				instance.__updateChildUIs()

class ChildUI( IECoreMaya.UIElement ) :

	def __init__( self, parameter, **kw ) :
		
		IECoreMaya.UIElement.__init__( self, maya.cmds.columnLayout() )
		
		if not isinstance( self.parent(), ClassVectorParameterUI ) :
			raise RunTimeError( "Parent must be a ClassVectorParameterUI" )
		
		self.__kw = kw.copy()
		self.__kw["hierarchyDepth"] = self.__kw.get( "hierarchyDepth", -1 ) + 1
			
		self.__parameter = parameter
		
		headerFormLayout = maya.cmds.formLayout()
		attachForm = []
		attachControl = []
				
		# triangle for expanding to view all parameters
		
		self.__parameterVisibilityIcon = maya.cmds.iconTextButton(
			style="iconOnly",
			height = 20,
			width = 20,
			image="arrowRight.xpm",
			command = self._createCallback( self.__toggleParameterVisibility ),
			annotation = "Show parameters",
		)
		
		attachForm += [
			( self.__parameterVisibilityIcon, "left",  IECoreMaya.CompoundParameterUI._labelIndent( self.__kw["hierarchyDepth"] ) ),
			( self.__parameterVisibilityIcon, "top", 0 ),
			( self.__parameterVisibilityIcon, "bottom", 0 ),
		]
		
		lastControl = self.__buildOptionalPreHeaderUI( headerFormLayout, attachForm, attachControl, self.__parameterVisibilityIcon )

		# layer icon

		layerIcon = maya.cmds.picture(
			width = 20,
			image = "%s.xpm" % self.__classIconName(),
			annotation = IECore.StringUtil.wrap(
				self.__class()[0].description + "\n\n" + "Click to reorder or remove.",
				48,
			)
		)
		IECoreMaya.createMenu( self.__layerMenu, layerIcon )
		IECoreMaya.createMenu( self.__layerMenu, layerIcon, button=1 )
		
		attachControl += [
			( layerIcon, "left", 0, lastControl ),
		]
		
		attachForm += [
			( layerIcon, "top", 0 ),
			( layerIcon, "bottom", 0 ),
		]
				
		# class specific fields
		
		self.__attributeChangedCallbackId = None
		self.__presetParameters = []
		self.__presetUIs = []

		self.__buildOptionalHeaderUI( headerFormLayout, attachForm, attachControl, layerIcon )
		
		maya.cmds.formLayout( 
			headerFormLayout,
			edit = True,
			attachForm = attachForm,
			attachControl = attachControl,
		)
		
		# CompoundParameterUI to hold child parameters
		
		maya.cmds.setParent( self._topLevelUI() )
		
		self.__compoundParameterUI = IECoreMaya.CompoundParameterUI( self.parent().node(), parameter, **kw )
		
		maya.cmds.frameLayout(
			self.__compoundParameterUI.layout(),
			edit = True,
			collapsable = True,
			labelVisible = False,
		)
				
	def _topLevelUIDeleted( self ) :
	
		self.__attributeChangedCallbackId = None
		
	def __class( self ) :
	
		classes = self.parent().parameter.getClasses( True )
		for c in classes :
			if c[1] == self.__parameter.name :
				return c
				
		raise RunTimeError( "Couldn't find class entry" )
		
	def __classVersionLabel( self ) :
	
		c = self.__class()
		
		return "version%d" % c[3]
				
	def __classVersionAnnotation( self ) :
	
		c = self.__class()
			
		return "%s v%d" % ( c[2], c[3] ) + "\n\nClick to change version"

	def __classIconName( self ) :
		
		c = self.__class()[0]
		
		iconName = "out_displayLayer"

		sources = []
		
		if hasattr( c, "blindData" ):
			sources.append( c.blindData() )
		
		if hasattr( c, "parameters" ):
			sources.append( c.parameters().userData() )
		
		for data in sources:	
			if "UI" in data and "icon" in data["UI"] :
				icon = data["UI"]["icon"].value
				if icon :
					return icon
	
		return iconName
	
	
	def __versionMenuDefinition( self ) :
	
		c = self.__class()
		
		# make a menu with just the versions in
			
		loader = IECore.ClassLoader.defaultLoader( self.parent().parameter.searchPathEnvVar() )
		result = IECore.MenuDefinition()
		for classVersion in loader.versions( c[2] ) :
					
			result.append(

				"/%d" % classVersion, 

				IECore.MenuItemDefinition(
					command = IECore.curry( self.parent()._setClass, self.__parameter.name, c[2], classVersion ),
					active = c[3] != classVersion
				)

			)
			
		return result

	def __toggleParameterVisibility( self ) :
			
		collapsed = not self.__compoundParameterUI.getCollapsed()
		self.__compoundParameterUI.setCollapsed( collapsed )
		
		image = "arrowRight.xpm" if collapsed else "arrowDown.xpm"
		annotation = "Show parameters" if collapsed else "Hide parameters" 
		maya.cmds.iconTextButton(
			self.__parameterVisibilityIcon,
			edit = True,
			image = image,
			annotation = annotation,
		)
	
	def __layerMenu( self ) :
	
		result = IECore.MenuDefinition()
		
		layerNames = self.parent().parameter.keys()
		layerIndex = layerNames.index( self.__parameter.name )
		
		result.append(
			"/Move/To Top",
			IECore.MenuItemDefinition(
				command = IECore.curry( self.__moveLayer, layerIndex, 0 ),
				active = layerIndex != 0
			)
		)
		
		result.append(
			"/Move/Up",
			IECore.MenuItemDefinition(
				command = IECore.curry( self.__moveLayer, layerIndex, layerIndex-1 ),
				active = layerIndex >= 1
			)
		)
		
		result.append(
			"/Move/Down",
			IECore.MenuItemDefinition(
				command = IECore.curry( self.__moveLayer, layerIndex, layerIndex+1 ),
				active = layerIndex < len( layerNames ) - 1
			)
		)
		
		result.append(
			"/Move/To Bottom",
			IECore.MenuItemDefinition(
				command = IECore.curry( self.__moveLayer, layerIndex, len( layerNames ) - 1 ),
				active = layerIndex < len( layerNames ) - 1
			)
		)
		
		result.append(
			"/RemoveSeparator",
			IECore.MenuItemDefinition(
				divider = True,
			)
		)
		
		# This has to be deferred as we update the UI from within the _removeClass method.
		# Unles it is, maya will crash as its still preoccupied with the popup menu.
		result.append(
			"/Remove",
			IECore.MenuItemDefinition(
				command = IECore.curry( maya.cmds.evalDeferred, IECore.curry( self.parent()._removeClass, self.__parameter.name ) )
			)
		)
		
		result.append(
			"/VersionSeparator",
			IECore.MenuItemDefinition(
				divider = True,
			)
		)
		
		result.append( 
			"/%s" % self.__classVersionLabel(),
			IECore.MenuItemDefinition(
				subMenu = self.__versionMenuDefinition
			)
		)
		
		return result
		
	def __moveLayer( self, oldIndex, newIndex ) :
	
		classes = [ c[1:] for c in self.parent().parameter.getClasses( True ) ]
		cl = classes[oldIndex]
		del classes[oldIndex]
		classes[newIndex:newIndex] = [ cl ]
				
		fnPH = IECoreMaya.FnParameterisedHolder( self.parent().node() )
		fnPH.setClassVectorParameterClasses( self.parent().parameter, classes )


	def __buildOptionalPreHeaderUI( self, formLayout, attachForm, attachControl, lastControl ) :
		
		return self.__drawHeaderParameterControls( formLayout, attachForm, attachControl, lastControl, "classVectorParameterPreHeader" )

	def __buildOptionalHeaderUI( self, formLayout, attachForm, attachControl, lastControl ) :
			
		labelPlugPath = self.__labelPlugPath()
		if labelPlugPath :
			
			self.__label = maya.cmds.text(
				parent = formLayout,
				align = "left",
				label = maya.cmds.getAttr( labelPlugPath ),
				font = IECoreMaya.CompoundParameterUI._labelFont( self.__kw["hierarchyDepth"] ),
				annotation = IECore.StringUtil.wrap( self.__parameter["label"].description, 48 ),
				width = 190 - IECoreMaya.CompoundParameterUI._labelIndent( self.__kw["hierarchyDepth"] ),
				recomputeSize = False,
			)
			
			renameMenu = IECore.MenuDefinition(
				[
					( "Change label...", { "command" : self.__changeLabel } ),
				]
			)
			IECoreMaya.createMenu( renameMenu, self.__label )
			IECoreMaya.createMenu( renameMenu, self.__label, button = 1 )
			
			attachForm += [
				( self.__label, "top", 0 ),
				( self.__label, "bottom", 0 ),
			]
			attachControl += [
				( self.__label, "left", 4, lastControl ),
			]
			
			lastControl = self.__label
			
		return self.__drawHeaderParameterControls( formLayout, attachForm, attachControl, lastControl, "classVectorParameterHeader" )
		
		
	def __drawHeaderParameterControls( self, formLayout, attachForm, attachControl, lastControl, uiKey ) :
	
		fnPH = IECoreMaya.FnParameterisedHolder( self.parent().node() )
		for parameter in self.__parameter.values() :
			
			forHeader = False
			with IECore.IgnoredExceptions( KeyError ) :
				forHeader = parameter.userData()["UI"][ uiKey ].value
				
			if forHeader :
				
				control = self.__drawHeaderParameterControl( parameter, fnPH )
						
				if control :
				
					attachForm +=  [
						( control, "top", 0 ),
						( control, "bottom", 0 ),
					]
					attachControl += [
						( control, "left", 0, lastControl ),
					]

					lastControl = control
		
		return lastControl
					

	def __drawHeaderParameterControl( self, parameter, fnPH ) :
		
		## \todo This would be so much easier if we could just use ParameterUI
		# instances for each of the controls. We can't because they all do their
		# own labelling and are layed out for an attribute editor. if we do the
		# todo in ParameterUI to remove the labels and stuff then we can do the
		# todo here.
		
		control = None 
		
		parameterPlugPath = fnPH.parameterPlugPath( parameter )
		annotation = IECore.StringUtil.wrap( "%s\n\n%s" % ( parameterPlugPath.split( "." )[1], parameter.description ), 48 )
		if parameter.presetsOnly :

			control = maya.cmds.iconTextStaticLabel(
				image = "arrowDown.xpm",
				font = "smallBoldLabelFont",
				style = "iconAndTextHorizontal",
				height = 23,
				width = 80,
				annotation = annotation,
			)
			IECoreMaya.createMenu( IECore.curry( self.__presetsMenu, parameter ), control )
			IECoreMaya.createMenu( IECore.curry( self.__presetsMenu, parameter ), control, button=1 )
			self.__presetParameters.append( parameter )
			self.__presetUIs.append( control )
			if self.__attributeChangedCallbackId is None :
				self.__attributeChangedCallbackId = IECoreMaya.CallbackId(
					maya.OpenMaya.MNodeMessage.addAttributeChangedCallback( self.parent().node(), self.__attributeChanged )
				)

			self.__updatePresetLabel( len( self.__presetUIs ) - 1 )

		elif isinstance( parameter, IECore.BoolParameter ) :

			control = maya.cmds.checkBox( label="", annotation=annotation )
			maya.cmds.connectControl( control, parameterPlugPath )

		elif isinstance( parameter, IECore.FloatParameter ) :

			control = maya.cmds.floatField(
				annotation = annotation,
				minValue = parameter.minValue,
				maxValue = parameter.maxValue,
				width = 45,
				pre = 2
			)
			maya.cmds.connectControl( control, parameterPlugPath )

		elif isinstance( parameter, IECore.Color3fParameter ) :

			control = maya.cmds.attrColorSliderGrp(
				label = "",
				columnWidth = ( ( 1, 1 ), ( 2, 50 ) ),
				columnAttach = ( ( 1, "both", 0 ), ( 2, "left", 0  ) ),
				attribute = parameterPlugPath,
				annotation = annotation,
				width = 50,
				showButton = False
			)

		else :

			IECore.msg( IECore.Msg.Level.Warning, "ClassVectorParameterUI", "Parameter \"%s\" has unsupported type for inclusion in header ( %s )." % ( parameter.name, parameter.typeName() ) )
		
		return control

	def __labelPlugPath( self ) :
	
		if "label" in self.__parameter :
			fnPH = IECoreMaya.FnParameterisedHolder( self.parent().node() )
			return fnPH.parameterPlugPath( self.__parameter["label"] )
			
		return ""
		
	def __changeLabel( self ) :
	
		labelPlugPath = self.__labelPlugPath()
	
		result = maya.cmds.promptDialog(
			title = "Change label",
			message = "New label : ",
			text = maya.cmds.getAttr( labelPlugPath ),
			button = [ "Change", "Cancel" ],
			defaultButton = "Change",
			cancelButton = "Cancel",
		)	
		
		if result == "Change" :
			newLabel = maya.cmds.promptDialog( query=True, text=True )
			maya.cmds.setAttr( labelPlugPath, newLabel, type="string" )
			maya.cmds.text(
				self.__label,
				edit = True,
				label = newLabel
			)
	
	def __presetsMenu( self, parameter ) :
	
		result = IECore.MenuDefinition()
		for p in parameter.presetNames() :
			result.append( "/" + p, { "command" : IECore.curry( self.__setPreset, parameter, p ) } )
			
		return result
		
	def __setPreset( self, parameter, name ) :
	
		parameter.setValue( name )
		IECoreMaya.FnParameterisedHolder( self.parent().node() ).setNodeValue( parameter )

	def __attributeChanged( self, changeType, plug, otherPlug, userData ) :
				
		if not ( changeType & maya.OpenMaya.MNodeMessage.kAttributeSet ) :
			return
		
		fnPH = IECoreMaya.FnParameterisedHolder( self.parent().node() )
		for index, parameter in enumerate( self.__presetParameters ) :
			
			try :
				myPlug = fnPH.parameterPlug( parameter )
			except :
				# this situation can occur when our parameter has been removed but the
				# ui we represent is not quite yet dead
				continue
		
			if plug == myPlug :
				self.__updatePresetLabel( index )
				
	def __updatePresetLabel( self, index ) :
	
		maya.cmds.iconTextStaticLabel( 
			self.__presetUIs[index],
			edit = True,
			label = self.__presetParameters[index].getCurrentPresetName()
		)
									
IECoreMaya.FnParameterisedHolder.addSetClassVectorParameterClassesCallback( ClassVectorParameterUI._classesSetCallback )
					
IECoreMaya.ParameterUI.registerUI( IECore.ClassVectorParameter.staticTypeId(), ClassVectorParameterUI )