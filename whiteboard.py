import wx
import os
import thread
import traceback
import sys
import numpy
from debug import log
import levelformat as lf
from pprint import pprint
import pickle

# deferred pygame imports
global pygame
global canvas
global renderer
global objects


class SDLPanel(wx.Panel):
    def __init__(self, parent, ID, tplSize):
        global pygame, level, renderer, objects
        wx.Panel.__init__(self, parent, ID, size=tplSize)
        self.Fit()
        
        # initialize pygame-related stuff
        os.environ['SDL_WINDOWID'] = str(self.GetHandle())
        os.environ['SDL_VIDEODRIVER'] = 'windib'       
        import pygame  # this has to happen after setting the environment variables.
        import canvas
        import renderer
        import objects
        pygame.display.init()
        screen = pygame.display.set_mode(tplSize)        
        
        # initialize level viewer
        self.screen = screen
        self.viewer = Viewer(screen, tplSize)
        # self.levelViewer.setLevel(level.Level(os.path.join("assets", "levels", "0.p"), self.levelViewer))
        # self.levelViewer.setLevel(level.Level(os.path.join("assets", "levels", "test.lvl"), self.levelViewer))
        self.viewer.setCanvas(canvas.Canvas(self.viewer))
        
        # start pygame thread
        thread.start_new_thread(self.viewer.mainLoop, ())

    def __del__(self):
        self.levelViewer.running = False


class Camera(object):
    def __init__(self, pos, game):
        self.translate = numpy.array([-game.width / 2, -game.height / 2])
        self.pos = pos + self.translate
        
    def update(self, game):        
        return self.pos
        
    def offset(self, o):
        self.pos += o


class Viewer(object):
    def __init__(self, screen, size):
        self.screen = screen
        self.width, self.height = size
        self.running = False

    def setCanvas(self, level):
        self.renderer = renderer.GameRenderer(self)
        self.level = level
        self.camera = Camera((0, 0), self)        
        self.renderer.add(self.level)
        self.avatars = pygame.sprite.Group()
        
        self.scroll = False
        self.selectedObject = None
        self.activeTool = None

    def update(self):
        self.camera.update(self)
        self.renderer.update(self)

    def draw(self):
        self.renderer.draw()
        
    def mainLoop(self):
        self.running = True
        try:
            while self.running:
                for event in pygame.event.get():
                    # log(event)
                    
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        x, y = event.pos
                        if event.button == 3:
                            self.onRightMouseButtonDown(x, y)                        
                        elif event.button == 1:
                            self.onLeftMouseButtonDown(x, y)
                            
                    if event.type == pygame.MOUSEBUTTONUP:                        
                        if event.button == 3:
                            self.onRightMouseButtonUp()
                        elif event.button == 1:
                            self.onLeftMouseButtonUp()
                                
                    if event.type == pygame.MOUSEMOTION:
                        self.onMouseMove(*(event.pos + event.rel))
                    
                self.update()
                self.draw()
            
        except:
            e, v, tb = sys.exc_info()
            print v
            traceback.print_tb(tb)
    
    def onRightMouseButtonDown(self, x, y):
        self.scroll = True
    
    def onLeftMouseButtonDown(self, x, y):
        if self.activeTool is None:  # select object
            matches = filter(lambda o: o.rect.collidepoint((x, y)), self.level.sprites())
            if len(matches) > 0:
                self.selectedObject = matches[0]
                log("selected", self.selectedObject)
                
        else:
            pos = numpy.array([x, y]) + self.camera.pos
            createdObject = self.activeTool.startPos(pos[0], pos[1])
            if createdObject is not None:                          
                self.selectedObject = createdObject 
                self.level.add(createdObject)
    
    def onRightMouseButtonUp(self):
        self.scroll = False
    
    def onLeftMouseButtonUp(self):
        if self.activeTool is not None:
            self.activeTool.end()
        #self.activeTool = None
        self.selectedObject = None
    
    def onMouseMove(self, x, y, dx, dy):
        if self.scroll:                     
            self.camera.offset(numpy.array([-dx, -dy]))
            
        elif self.activeTool is None:  # move selected object
            if self.selectedObject is not None:
                self.selectedObject.offset(dx, dy)
                
        else: 
            pos = numpy.array([x, y]) + self.camera.pos
            self.activeTool.addPos(*pos)

class Tool(object):
    def __init__(self, name, viewer):
        self.name = name
        self.viewer = viewer
        self.camera = viewer.camera
        self.obj = None
    
    def startPos(self, x, y):
        pass
    
    def addPos(self, x, y):
        pass
    
    def end(self):
        self.obj = None

class RectTool(Tool):
    def __init__(self, viewer):
        Tool.__init__(self, "rectangle", viewer)
    
    def startPos(self, x, y):
        self.obj = objects.Rectangle(lf.Platform(x, y, 10, 10), self.viewer)
        return self.obj
            
    def addPos(self, x, y):
        if self.obj is None: return
        topLeft = numpy.array([self.obj.rect.left, self.obj.rect.top]) 
        pos = numpy.array([x, y]) - self.camera.pos
        dim = pos - topLeft
        print dim
        if dim[0] > 0 and dim[1] > 0:
            self.obj.setSize(dim[0], dim[1])
            self.obj.rect.topleft = topLeft
            self.obj.pos = numpy.array(self.obj.rect.center) + self.camera.pos

class PenTool(Tool):
    def __init__(self, viewer):
        Tool.__init__(self, "pen", viewer)
        self.lineWidth = 3
        self.margin = 2*self.lineWidth
        self.color = (0, 0, 0)
    
    def startPos(self, x, y):
        self.lineStartPos = numpy.array([x, y])
        surface = pygame.Surface((self.margin, self.margin))#, pygame.SRCALPHA)
        surface.fill((255, 0, 255))
        surface.set_colorkey((255, 0, 255))
        self.surface = surface
        self.translateOrigin = numpy.array([-x, -y])
        self.obj = objects.Scribble({"wrect": pygame.Rect(x - self.margin / 2, y - self.margin / 2, 1, 1), "image": surface.convert()}, self.viewer)
        self.minX = self.maxX = x
        self.minY = self.maxY = y 
        return self.obj
    
    def addPos(self, x, y):
        if self.obj is None: return
        
        # determine growth
        print "\nminX=%d maxX=%d" % (self.minX, self.maxX)
        print "x=%d y=%d" % (x,y)        
        growRight = x - self.maxX if x > self.maxX else 0
        growLeft = self.minX - x if x < self.minX else 0
        growBottom = y - self.maxY if y > self.maxY else 0
        growTop = self.minY - y if y < self.minY else 0
        print "grow: right=%d left=%d top=%d bottom=%d" % (growRight, growLeft, growTop, growBottom)
        self.maxX = max(self.maxX, x)
        self.maxY = max(self.maxY, y)
        self.minX = min(self.minX, x)
        self.minY = min(self.minY, y)
        print "new: minX=%d maxX=%d" % (self.minX, self.maxX)
        
        # create new larger surface and copy old surface content
        margin = self.margin
        oldWidth = self.surface.get_width() 
        oldHeight = self.surface.get_height() 
        newWidth = oldWidth + growLeft + growRight
        newHeight = oldHeight + growBottom + growTop
        print "newDim: (%d, %d)" % (newWidth, newHeight)
        surface = pygame.Surface((newWidth, newHeight))#, pygame.SRCALPHA)
        surface.fill((255, 0, 255))
        surface.set_colorkey((255, 0, 255))
        surface.blit(self.surface, (growLeft, growTop))
        self.surface = surface
        
        # apply new surface and translate pos
        self.obj.setSurface(self.surface)
        self.obj.offset(-growLeft, -growTop)
        
        # draw line
        self.translateOrigin = -self.obj.pos + numpy.array([-margin, -margin])
        print "translateOrigin=%s" % str(self.translateOrigin) 
        marginTranslate = numpy.array([margin, margin])
        pos1 = self.lineStartPos + self.translateOrigin + marginTranslate 
        pos2 = numpy.array([x, y]) + self.translateOrigin + marginTranslate
        print "drawing from %s to %s" % (str(pos1), str(pos2))
        pygame.draw.line(self.surface, self.color, pos1, pos2, self.lineWidth)
        self.lineStartPos = numpy.array([x, y])        

class WhiteboardFrame(wx.Frame):
    def __init__(self, parent, ID, strTitle, tplSize):
        wx.Frame.__init__(self, parent, ID, strTitle, size=tplSize)
        self.pnlSDL = SDLPanel(self, -1, tplSize)
        
        # Menu Bar        
        self.frame_menubar = wx.MenuBar()
        self.SetMenuBar(self.frame_menubar)
        # - file Menu
        self.file_menu = wx.Menu()
        self.file_menu.Append(1, "&Open", "Open from file..")
        self.file_menu.Append(2, "&Save", "Open a file..")
        self.file_menu.AppendSeparator()
        self.file_menu.Append(3, "&Close", "Quit")
        self.Bind(wx.EVT_MENU, self.onOpen, id=1)
        self.Bind(wx.EVT_MENU, self.onSave, id=2)
        self.Bind(wx.EVT_MENU, self.onExit, id=3)
        self.frame_menubar.Append(self.file_menu, "File")

        self.viewer = self.pnlSDL.viewer
        
        toolbar = wx.Panel(self)
        self.toolbar = toolbar
        tools = [
             PenTool(self.viewer),
             RectTool(self.viewer)
        ]
        box = wx.BoxSizer(wx.HORIZONTAL)
        for i, tool in enumerate(tools):
            print "init tool %s" % tool.name
            btn = wx.Button(toolbar, label=tool.name)
            self.Bind(wx.EVT_BUTTON, lambda evt, tool=tool: self.onSelectTool(tool), btn)
            box.Add(btn)
        toolbar.SetSizer(box)
            
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(toolbar, flag=wx.EXPAND | wx.BOTTOM, border=0)
        sizer.Add(self.pnlSDL, 1, flag=wx.EXPAND)
        self.SetSizer(sizer)

    def onSelectTool(self, tool):
        self.viewer.activeTool = tool
        print "selected tool %s" % tool.name

    def onOpen(self, event):
        dlg = wx.FileDialog(self, "Choose a file", os.path.join(".", "assets", "levels"), "", "*.lvl", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            path = os.path.join(dlg.GetDirectory(), dlg.GetFilename())                        
            dlg.Destroy()
            
            # load level
            self.viewer.setLevel(level.Level(path, self.viewer))
    
    def onSave(self, event):
        dlg = wx.FileDialog(self, "Choose a file", os.path.join(".", "assets", "levels"), "", "*.lvl", wx.SAVE)
        if dlg.ShowModal() == wx.ID_OK:
            path = os.path.join(dlg.GetDirectory(), dlg.GetFilename())                        
            dlg.Destroy()
            
            # save level
            f = file(path, "wb")
            pickle.dump(self.viewer.level.saveFormat(), f)
            f.close()

    def onExit(self, event):
        pass


if __name__ == '__main__':
    app = wx.PySimpleApp()
    frame = WhiteboardFrame(None, wx.ID_ANY, "wYPeboard", (800, 600))
    frame.Show()
    app.MainLoop()
