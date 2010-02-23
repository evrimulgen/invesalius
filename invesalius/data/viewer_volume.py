#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
#--------------------------------------------------------------------------

import sys

import wx
import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
import wx.lib.pubsub as ps

import constants as const
import data.vtk_utils as vtku
import project as prj
import style as st
import utils

from data import measures

class Viewer(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320, 320))
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        self.interaction_style = st.StyleStateManager()

        style =  vtk.vtkInteractorStyleTrackballCamera()
        self.style = style

        interactor = wxVTKRenderWindowInteractor(self, -1, size = self.GetSize())
        interactor.SetInteractorStyle(style)
        self.interactor = interactor

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(interactor, 1, wx.EXPAND)
        self.sizer = sizer
        self.SetSizer(sizer)
        self.Layout()

        # It would be more correct (API-wise) to call interactor.Initialize() and
        # interactor.Start() here, but Initialize() calls RenderWindow.Render().
        # That Render() call will get through before we can setup the
        # RenderWindow() to render via the wxWidgets-created context; this
        # causes flashing on some platforms and downright breaks things on
        # other platforms.  Instead, we call widget.Enable().  This means
        # that the RWI::Initialized ivar is not set, but in THIS SPECIFIC CASE,
        # that doesn't matter.
        interactor.Enable(1)

        ren = vtk.vtkRenderer()
        interactor.GetRenderWindow().AddRenderer(ren)
        self.ren = ren

        self.raycasting_volume = False

        self.onclick = False

        self.text = vtku.Text()
        self.text.SetValue("")
        self.ren.AddActor(self.text.actor)


        self.slice_plane = None

        self.view_angle = None

        self.__bind_events()
        self.__bind_events_wx()

        self.mouse_pressed = 0
        self.on_wl = False

        self.picker = vtk.vtkPointPicker()
        interactor.SetPicker(self.picker)
        self.seed_points = []

        self.points_reference = []

        self.measure_picker = vtk.vtkPointPicker()
        self.measure_picker.SetTolerance(0.005)
        self.measures = []
        

    def __bind_events(self):
        ps.Publisher().subscribe(self.LoadActor,
                                 'Load surface actor into viewer')
        ps.Publisher().subscribe(self.RemoveActor,
                                'Remove surface actor from viewer')
        ps.Publisher().subscribe(self.UpdateRender,
                                 'Render volume viewer')
        ps.Publisher().subscribe(self.ChangeBackgroundColour,
                        'Change volume viewer background colour')
        # Raycating - related
        ps.Publisher().subscribe(self.LoadVolume,
                                 'Load volume into viewer')
        ps.Publisher().subscribe(self.OnSetWindowLevelText,
                            'Set volume window and level text')
        ps.Publisher().subscribe(self.OnHideRaycasting,
                                'Hide raycasting volume')
        ps.Publisher().subscribe(self.OnShowRaycasting,
                                'Update raycasting preset')
        ###
        ps.Publisher().subscribe(self.AppendActor,'AppendActor')
        ps.Publisher().subscribe(self.SetWidgetInteractor, 
                                'Set Widget Interactor')
        ps.Publisher().subscribe(self.OnSetViewAngle,
                                'Set volume view angle')

        ps.Publisher().subscribe(self.OnDisableBrightContrast,
                                 ('Set interaction mode',
                                  const.MODE_SLICE_EDITOR))

        ps.Publisher().subscribe(self.OnExportSurface, 'Export surface to file')

        ps.Publisher().subscribe(self.LoadSlicePlane, 'Load slice plane')

        ps.Publisher().subscribe(self.ResetCamClippingRange, 'Reset cam clipping range')

        ps.Publisher().subscribe(self.OnEnableStyle, 'Enable style')
        ps.Publisher().subscribe(self.OnDisableStyle, 'Disable style')

        ps.Publisher().subscribe(self.OnHideText,
                                 'Hide text actors on viewers')

        ps.Publisher().subscribe(self.OnShowText,
                                 'Show text actors on viewers')
        ps.Publisher().subscribe(self.OnCloseProject, 'Close project data')

        ps.Publisher().subscribe(self.RemoveAllActor, 'Remove all volume actors')
        
        ps.Publisher().subscribe(self.OnExportPicture,'Export picture to file')

        ps.Publisher().subscribe(self.OnStartSeed,'Create surface by seeding - start')
        ps.Publisher().subscribe(self.OnEndSeed,'Create surface by seeding - end')

    def OnStartSeed(self, pubsub_evt):
        index = pubsub_evt.data
        self.seed_points = []
    
    def OnEndSeed(self, pubsub_evt):
        ps.Publisher().sendMessage("Create surface from seeds",
                                    self.seed_points) 

    def OnExportPicture(self, pubsub_evt):
        ps.Publisher().sendMessage('Begin busy cursor')
        id, filename, filetype = pubsub_evt.data
        
        if id == const.VOLUME:
            if filetype == const.FILETYPE_POV:
                renwin = self.interactor.GetRenderWindow()
                image = vtk.vtkWindowToImageFilter()
                image.SetInput(renwin)
                writer = vtk.vtkPOVExporter()
                writer.SetFileName(filename)
                writer.SetRenderWindow(renwin)
                writer.Write()
            else:
                #Use tiling to generate a large rendering.
                image = vtk.vtkRenderLargeImage()
                image.SetInput(self.ren)
                image.SetMagnification(1)

                image = image.GetOutput()


                # write image file
                if (filetype == const.FILETYPE_BMP):
                    writer = vtk.vtkBMPWriter()
                elif (filetype == const.FILETYPE_JPG):
                    writer =  vtk.vtkJPEGWriter()
                elif (filetype == const.FILETYPE_PNG):
                    writer = vtk.vtkPNGWriter()
                elif (filetype == const.FILETYPE_PS):
                    writer = vtk.vtkPostScriptWriter()
                elif (filetype == const.FILETYPE_TIF):
                    writer = vtk.vtkTIFFWriter()
                    filename = "%s.tif"%filename.strip(".tif")
                
                writer.SetInput(image)
                writer.SetFileName(filename)
                writer.Write()
        ps.Publisher().sendMessage('End busy cursor')


 
    def OnCloseProject(self, pubsub_evt):
        if self.raycasting_volume:
            self.raycasting_volume = False
            
        if  self.slice_plane:
            self.slice_plane.Disable()
            self.slice_plane.DeletePlanes()
            del self.slice_plane
            ps.Publisher().sendMessage('Uncheck image plane menu')
            self.mouse_pressed = 0
            self.on_wl = False
            self.slice_plane = 0

    def OnHideText(self, pubsub_evt):
        self.text.Hide()
        self.interactor.Render()

    def OnShowText(self, pubsub_evt):
        if self.on_wl:
            self.text.Show()
            self.interactor.Render()

    def AddPointReference(self, position, radius=1, colour=(1, 0, 0)):
        """
        Add a point representation in the given x,y,z position with a optional
        radius and colour.
        """
        point = vtk.vtkSphereSource()
        point.SetCenter(position)
        point.SetRadius(radius)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInput(point.GetOutput())

        p = vtk.vtkProperty()
        p.SetColor(colour)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(p)
        actor.PickableOff()

        self.ren.AddActor(actor)

        self.points_reference.append(actor)

    def RemoveAllPointsReference(self):
        for actor in self.points_reference:
            self.ren.RemoveActor(actor)
        self.points_reference = []

    def RemovePointReference(self, point):
        """
        Remove the point reference. The point argument is the position that is
        added.
        """
        actor = self.points_reference.pop(point)
        self.ren.RemoveActor(actor)

    def __bind_events_wx(self):
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        pass

    def SetInteractorStyle(self, state):
        action = {
              const.STATE_PAN:
                    {
                    "MouseMoveEvent": self.OnPanMove,
                    "LeftButtonPressEvent": self.OnPanClick,
                    "LeftButtonReleaseEvent": self.OnReleasePanClick
                    },
              const.STATE_ZOOM:
                    {
                    "MouseMoveEvent": self.OnZoomMove,
                    "LeftButtonPressEvent": self.OnZoomClick,
                    "LeftButtonReleaseEvent": self.OnReleaseZoomClick,
                    },
              const.STATE_SPIN:
                    {
                    "MouseMoveEvent": self.OnSpinMove,
                    "LeftButtonPressEvent": self.OnSpinClick,
                    "LeftButtonReleaseEvent": self.OnReleaseSpinClick,
                    },
              const.STATE_WL:
                    { 
                    "MouseMoveEvent": self.OnWindowLevelMove,
                    "LeftButtonPressEvent": self.OnWindowLevelClick,
                    "LeftButtonReleaseEvent":self.OnWindowLevelRelease
                    },
              const.STATE_DEFAULT:
                    {
                    },
              const.VOLUME_STATE_SEED:
                    {
                    "LeftButtonPressEvent": self.OnInsertSeed
                    },
              const.STATE_LINEAR_MEASURE:
                  {
                  "LeftButtonPressEvent": self.OnInsertLinearMeasurePoint
                  }
              }

        if state == const.STATE_WL:
            self.on_wl = True
            if self.raycasting_volume:
                self.text.Show()
                self.interactor.Render()
        else:
            self.on_wl = False
            self.text.Hide()
            self.interactor.Render()

        if (state == const.STATE_ZOOM_SL):
            style = vtk.vtkInteractorStyleRubberBandZoom()
            self.interactor.SetInteractorStyle(style)
            self.style = style
        else:
            style = vtk.vtkInteractorStyleTrackballCamera()
            self.interactor.SetInteractorStyle(style)
            self.style = style  

        if state == const.STATE_LINEAR_MEASURE:
            self.interactor.SetPicker(self.measure_picker)

            # Check each event available for each mode
            for event in action[state]:
                # Bind event
                style.AddObserver(event,action[state][event])

    def OnSpinMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Spin()
            evt.OnRightButtonDown()

    def OnSpinClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartSpin()

    def OnReleaseSpinClick(self,evt,obj):
        self.mouse_pressed = 0
        evt.EndSpin()

    def OnZoomMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Dolly()
            evt.OnRightButtonDown()

    def OnZoomClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartDolly()

    def OnReleaseZoomClick(self,evt,obj):
        self.mouse_pressed = 0
        evt.EndDolly()

    def OnPanMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Pan()
            evt.OnRightButtonDown()

    def OnPanClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartPan()

    def OnReleasePanClick(self,evt,obj):
        self.mouse_pressed = 0
        evt.EndPan()

    def OnWindowLevelMove(self, obj, evt):
        if self.onclick and self.raycasting_volume:
            mouse_x, mouse_y = self.interactor.GetEventPosition()
            diff_x = mouse_x - self.last_x
            diff_y = mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y
            ps.Publisher().sendMessage('Set raycasting relative window and level',
                (diff_x, diff_y))
            ps.Publisher().sendMessage('Refresh raycasting widget points', None)
            self.interactor.Render()

    def OnWindowLevelClick(self, obj, evt):
        if const.RAYCASTING_WWWL_BLUR:
            self.style.StartZoom()
        self.onclick = True
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        self.last_x, self.last_y = mouse_x, mouse_y

    def OnWindowLevelRelease(self, obj, evt):
        self.onclick = False
        if const.RAYCASTING_WWWL_BLUR:
            self.style.EndZoom()

    def OnEnableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        if (state in const.VOLUME_STYLES):
            new_state = self.interaction_style.AddState(state)
            self.SetInteractorStyle(new_state)
        else:
            new_state = self.interaction_style.RemoveState(state)
            self.SetInteractorStyle(new_state)

    def OnDisableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        new_state = self.interaction_style.RemoveState(state)
        self.SetInteractorStyle(new_state)

    def ResetCamClippingRange(self, pubsub_evt):
        self.ren.ResetCamera()
        self.ren.ResetCameraClippingRange()

    def OnExportSurface(self, pubsub_evt):
        filename, filetype = pubsub_evt.data
        fileprefix = filename.split(".")[-2]
        renwin = self.interactor.GetRenderWindow()

        if filetype == const.FILETYPE_RIB:
            writer = vtk.vtkRIBExporter()
            writer.SetFilePrefix(fileprefix)
            writer.SetTexturePrefix(fileprefix)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_VRML:
            writer = vtk.vtkVRMLExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_OBJ:
            writer = vtk.vtkOBJExporter()
            writer.SetFilePrefix(fileprefix)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_IV:
            writer = vtk.vtkIVExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
            writer.Write()

    def OnEnableBrightContrast(self, pubsub_evt):
        style = self.style
        style.AddObserver("MouseMoveEvent", self.OnMove)
        style.AddObserver("LeftButtonPressEvent", self.OnClick)
        style.AddObserver("LeftButtonReleaseEvent", self.OnRelease)

    def OnDisableBrightContrast(self, pubsub_evt):
        style = vtk.vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(style)
        self.style = style

    def OnSetWindowLevelText(self, pubsub_evt):
        if self.raycasting_volume:
            ww, wl = pubsub_evt.data
            self.text.SetValue("WL: %d  WW: %d"%(wl, ww))

    def OnShowRaycasting(self, pubsub_evt):
        self.raycasting_volume = True
        if self.on_wl:
            self.text.Show()

    def OnHideRaycasting(self, pubsub_evt):
        self.raycasting_volume = False
        self.text.Hide()

    def OnSize(self, evt):
        self.UpdateRender()
        self.Refresh()
        self.interactor.UpdateWindowUI()
        self.interactor.Update()
        evt.Skip()

    def ChangeBackgroundColour(self, pubsub_evt):
        colour = pubsub_evt.data
        self.ren.SetBackground(colour)
        self.UpdateRender()

    def LoadActor(self, pubsub_evt):
        actor = pubsub_evt.data

        ren = self.ren
        ren.AddActor(actor)

        if not (self.view_angle):
            self.SetViewAngle(const.VOL_FRONT)
            self.view_angle = 1
        else:
            ren.ResetCamera()
            ren.ResetCameraClippingRange()

        #self.ShowOrientationCube()
        self.interactor.Render()

    def RemoveActor(self, pubsub_evt):
        utils.debug("RemoveActor")
        actor = pubsub_evt.data
        ren = self.ren
        ren.RemoveActor(actor)
        self.interactor.Render()
        
    def RemoveAllActor(self, pubsub_evt):
        utils.debug("RemoveAllActor")
        self.ren.RemoveAllProps()
        ps.Publisher().sendMessage('Render volume viewer')

        
    def LoadSlicePlane(self, pubsub_evt):
        self.slice_plane = SlicePlane()

    def LoadVolume(self, pubsub_evt):
        self.raycasting_volume = True

        volume = pubsub_evt.data[0]
        colour = pubsub_evt.data[1]
        ww, wl = pubsub_evt.data[2]

        self.light = self.ren.GetLights().GetNextItem()

        self.ren.AddVolume(volume)
        self.text.SetValue("WL: %d  WW: %d"%(wl, ww))

        if self.on_wl:
            self.text.Show()
        else:
            self.text.Hide()

        self.ren.SetBackground(colour)

        if not (self.view_angle):
            self.SetViewAngle(const.VOL_FRONT)
        else:
            self.ren.ResetCamera()
            self.ren.ResetCameraClippingRange()

        self.UpdateRender()

    def OnSetViewAngle(self, evt_pubsub):
        view = evt_pubsub.data
        self.SetViewAngle(view)

    def SetViewAngle(self, view):
        cam = self.ren.GetActiveCamera()
        cam.SetFocalPoint(0,0,0)

        proj = prj.Project()
        orig_orien = proj.original_orientation

        xv,yv,zv = const.VOLUME_POSITION[orig_orien][0][view]
        xp,yp,zp = const.VOLUME_POSITION[orig_orien][1][view]

        cam.SetViewUp(xv,yv,zv)
        cam.SetPosition(xp,yp,zp)

        self.ren.ResetCameraClippingRange() 
        self.ren.ResetCamera()
        self.interactor.Render()

    def ShowOrientationCube(self):
        cube = vtk.vtkAnnotatedCubeActor()
        cube.GetXMinusFaceProperty().SetColor(1,0,0)
        cube.GetXPlusFaceProperty().SetColor(1,0,0)
        cube.GetYMinusFaceProperty().SetColor(0,1,0)
        cube.GetYPlusFaceProperty().SetColor(0,1,0)
        cube.GetZMinusFaceProperty().SetColor(0,0,1)
        cube.GetZPlusFaceProperty().SetColor(0,0,1)
        cube.GetTextEdgesProperty().SetColor(0,0,0)

        # anatomic labelling
        cube.SetXPlusFaceText ("A")
        cube.SetXMinusFaceText("P")
        cube.SetYPlusFaceText ("L")
        cube.SetYMinusFaceText("R")
        cube.SetZPlusFaceText ("S")
        cube.SetZMinusFaceText("I")

        axes = vtk.vtkAxesActor()
        axes.SetShaftTypeToCylinder()
        axes.SetTipTypeToCone()
        axes.SetXAxisLabelText("X")
        axes.SetYAxisLabelText("Y")
        axes.SetZAxisLabelText("Z")
        #axes.SetNormalizedLabelPosition(.5, .5, .5)

        orientation_widget = vtk.vtkOrientationMarkerWidget()
        orientation_widget.SetOrientationMarker(cube)
        orientation_widget.SetViewport(0.85,0.85,1.0,1.0)
        #orientation_widget.SetOrientationMarker(axes)
        orientation_widget.SetInteractor(self.interactor)
        orientation_widget.SetEnabled(1)
        orientation_widget.On()
        orientation_widget.InteractiveOff()

    def UpdateRender(self, evt_pubsub=None):
        self.interactor.Render()

    def SetWidgetInteractor(self, evt_pubsub=None):
        evt_pubsub.data.SetInteractor(self.interactor._Iren)

    def AppendActor(self, evt_pubsub=None):
        self.ren.AddActor(evt_pubsub.data)

    def OnInsertSeed(self, obj, evt):
        x,y = self.interactor.GetEventPosition()
        #x,y = obj.GetLastEventPosition()
        self.picker.Pick(x, y, 0, self.ren)
        point_id = self.picker.GetPointId()
        self.seed_points.append(point_id)
        self.interactor.Render()

    def OnInsertLinearMeasurePoint(self, obj, evt):
        print "Hey, you inserted measure point"
        x,y = self.interactor.GetEventPosition()
        self.measure_picker.Pick(x, y, 0, self.ren)
        x, y, z = self.measure_picker.GetPickPosition()
        if self.measure_picker.GetPointId() != -1: 
            if not self.measures or self.measures[-1].point_actor2:
                m = measures.LinearMeasure(self.ren)
                m.SetPoint1(x, y, z)
                self.measures.append(m)
            else:
                m = self.measures[-1]
                m.SetPoint2(x, y, z)
            self.interactor.Render()


class SlicePlane:
    def __init__(self):
        project = prj.Project()
        self.original_orientation = project.original_orientation
        self.Create()
        self.__bind_evt()
        self.__bind_vtk_evt()

    def __bind_evt(self):
        ps.Publisher().subscribe(self.Enable, 'Enable plane')
        ps.Publisher().subscribe(self.Disable, 'Disable plane')
        ps.Publisher().subscribe(self.ChangeSlice, 'Change slice from slice plane')

    def __bind_vtk_evt(self):
        self.plane_x.AddObserver("InteractionEvent", self.PlaneEvent)
        self.plane_y.AddObserver("InteractionEvent", self.PlaneEvent)
        self.plane_z.AddObserver("InteractionEvent", self.PlaneEvent)

    def PlaneEvent(self, obj, evt):
        number = obj.GetSliceIndex()
        plane_axis = obj.GetPlaneOrientation()
        if (self.original_orientation == const.AXIAL):
            if (plane_axis == 0):
                orientation = "SAGITAL"
            elif(plane_axis == 1):
                orientation = "CORONAL"
                dimen = obj.GetInput().GetDimensions()
                number = abs(dimen[0] - (number + 1))
            else:
                orientation = "AXIAL"

        elif(self.original_orientation == const.SAGITAL):
            if (plane_axis == 0):
                orientation = "CORONAL"
            elif(plane_axis == 1):
                orientation = "AXIAL"
                dimen = obj.GetInput().GetDimensions()
                number = abs(dimen[0] - (number + 1))
            else:
                orientation = "SAGITAL"
        else:
            if (plane_axis == 0):
                orientation = "SAGITAL"
            elif(plane_axis == 1):
                orientation = "AXIAL"
                dimen = obj.GetInput().GetDimensions()
                number = abs(dimen[0] - (number + 1))
            else:
                orientation = "CORONAL"

        if (obj.GetSlicePosition() != 0.0):
            ps.Publisher().sendMessage(('Set scroll position', \
                                        orientation), number)

    def Create(self):
        plane_x = self.plane_x = vtk.vtkImagePlaneWidget()
        plane_x.DisplayTextOff()
        ps.Publisher().sendMessage('Input Image in the widget', plane_x)
        plane_x.SetPlaneOrientationToXAxes()
        plane_x.TextureVisibilityOn()
        plane_x.SetLeftButtonAction(1)
        plane_x.SetRightButtonAction(0)
        prop1 = plane_x.GetPlaneProperty()
        prop1.SetColor(0, 0, 1)
        cursor_property = plane_x.GetCursorProperty()
        cursor_property.SetOpacity(0) 

        plane_y = self.plane_y = vtk.vtkImagePlaneWidget()
        plane_y.DisplayTextOff()
        ps.Publisher().sendMessage('Input Image in the widget', plane_y)
        plane_y.SetPlaneOrientationToYAxes()
        plane_y.TextureVisibilityOn()
        plane_y.SetLeftButtonAction(1)
        plane_y.SetRightButtonAction(0)
        prop1 = plane_y.GetPlaneProperty()
        prop1.SetColor(0, 1, 0)
        cursor_property = plane_y.GetCursorProperty()
        cursor_property.SetOpacity(0) 

        plane_z = self.plane_z = vtk.vtkImagePlaneWidget()
        plane_z.DisplayTextOff()
        ps.Publisher().sendMessage('Input Image in the widget', plane_z)
        plane_z.SetPlaneOrientationToZAxes()
        plane_z.TextureVisibilityOn()
        plane_z.SetLeftButtonAction(1)
        plane_z.SetRightButtonAction(0)
        prop1 = plane_z.GetPlaneProperty()
        prop1.SetColor(1, 0, 0)
        cursor_property = plane_z.GetCursorProperty()
        cursor_property.SetOpacity(0) 

        if(self.original_orientation == const.AXIAL):
            prop3 = plane_z.GetPlaneProperty()
            prop3.SetColor(1, 0, 0)

            prop1 = plane_x.GetPlaneProperty()
            prop1.SetColor(0, 0, 1)

            prop2 = plane_y.GetPlaneProperty()
            prop2.SetColor(0, 1, 0)

        elif(self.original_orientation == const.SAGITAL):
            prop3 = plane_y.GetPlaneProperty()
            prop3.SetColor(1, 0, 0)

            prop1 = plane_z.GetPlaneProperty()
            prop1.SetColor(0, 0, 1)

            prop2 = plane_x.GetPlaneProperty()
            prop2.SetColor(0, 1, 0)

        else:
            prop3 = plane_y.GetPlaneProperty()
            prop3.SetColor(1, 0, 0)

            prop1 = plane_x.GetPlaneProperty()
            prop1.SetColor(0, 0, 1)

            prop2 = plane_z.GetPlaneProperty()
            prop2.SetColor(0, 1, 0)

        ps.Publisher().sendMessage('Set Widget Interactor', plane_x)
        ps.Publisher().sendMessage('Set Widget Interactor', plane_y)
        ps.Publisher().sendMessage('Set Widget Interactor', plane_z)

        self.Render()

    def Enable(self, evt_pubsub=None):
        if (evt_pubsub):
            label = evt_pubsub.data

            if(self.original_orientation == const.AXIAL):
                if(label == "Axial"):
                    self.plane_z.On()
                elif(label == "Coronal"):
                    self.plane_y.On()
                elif(label == "Sagital"):
                    self.plane_x.On()
                    a = self.plane_x.GetTexturePlaneProperty()
                    a.SetBackfaceCulling(0)
                    c = self.plane_x.GetTexture()
                    c.SetRestrictPowerOf2ImageSmaller(1)

            elif(self.original_orientation == const.SAGITAL):
                if(label == "Axial"):
                    self.plane_y.On()
                elif(label == "Coronal"):
                    self.plane_x.On()
                elif(label == "Sagital"):
                    self.plane_z.On()
            else:
                if(label == "Axial"):
                    self.plane_y.On()
                elif(label == "Coronal"):
                    self.plane_z.On()
                elif(label == "Sagital"):
                    self.plane_x.On()

        else:
            self.plane_z.On()
            self.plane_x.On()
            self.plane_y.On()
            ps.Publisher().sendMessage('Set volume view angle', const.VOL_ISO)
        self.Render()

    def Disable(self, evt_pubsub=None):
        if (evt_pubsub):
            label = evt_pubsub.data

            if(self.original_orientation == const.AXIAL):
                if(label == "Axial"):
                    self.plane_z.Off()
                elif(label == "Coronal"):
                    self.plane_y.Off()
                elif(label == "Sagital"):
                    self.plane_x.Off()

            elif(self.original_orientation == const.SAGITAL):
                if(label == "Axial"):
                    self.plane_y.Off()
                elif(label == "Coronal"):
                    self.plane_x.Off()
                elif(label == "Sagital"):
                    self.plane_z.Off()
            else:
                if(label == "Axial"):
                    self.plane_y.Off()
                elif(label == "Coronal"):
                    self.plane_z.Off()
                elif(label == "Sagital"):
                    self.plane_x.Off()
        else:
            self.plane_z.Off()
            self.plane_x.Off()
            self.plane_y.Off()

        self.Render()

    def Render(self):
        ps.Publisher().sendMessage('Render volume viewer')    

    def ChangeSlice(self, pubsub_evt = None):
        orientation, number = pubsub_evt.data

        if (self.original_orientation == const.AXIAL):
            if (orientation == "CORONAL"):
                self.SetSliceNumber(number, "Y")
            elif(orientation == "SAGITAL"):
                self.SetSliceNumber(number, "X")
            else:
                self.SetSliceNumber(number, "Z")

        elif(self.original_orientation == const.SAGITAL):
            if (orientation == "CORONAL"):
                self.SetSliceNumber(number, "X")
            elif(orientation == "SAGITAL"):
                self.SetSliceNumber(number, "Z")
            else:
                self.SetSliceNumber(number, "Y")

        else:
            if (orientation == "CORONAL"):
                self.SetSliceNumber(number, "Z")
            elif(orientation == "SAGITAL"):
                self.SetSliceNumber(number, "X")
            else:
                self.SetSliceNumber(number, "Y")

        self.Render()

    def SetSliceNumber(self, number, axis):
        if (axis == "X"):
            self.plane_x.SetPlaneOrientationToXAxes()
            self.plane_x.SetSliceIndex(number)
        elif(axis == "Y"):
            self.plane_y.SetPlaneOrientationToYAxes()
            self.plane_y.SetSliceIndex(number)
        else:
            self.plane_z.SetPlaneOrientationToZAxes()
            self.plane_z.SetSliceIndex(number)

    def DeletePlanes(self):
        del self.plane_x
        del self.plane_y
        del self.plane_z 
    

