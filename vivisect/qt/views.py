
import vqt.tree as vq_tree
import vivisect.base as viv_base
import envi.qt.memory as e_q_memory
import visgraph.pathcore as vg_path
import envi.qt.memcanvas as e_q_memcanvas
import vivisect.qt.ctxmenu as v_q_ctxmenu

from PyQt4 import QtGui,QtCore

from vqt.main import *
from vqt.common import *
from vivisect.const import *

class VivNavModel(e_q_memory.EnviNavModel):
    pass

class VivView(VqtView, viv_base.VivEventCore):
    '''
    In any vivisect list/tree view, the first column will be
    an address expression.  Other than that, all bets are off.
    '''
    def __init__(self, vw, parent=None):
        VqtView.__init__(self, parent=parent)
        viv_base.VivEventCore.__init__(self, vw)
        self.vw = vw
        self.vivgui = vw.getVivGui()
        self.vivgui.addEventCore(self)

class VivLocModel(VqtModel):
    columns = ('Address','Location')

class VivLocView(VivView):

    def __init__(self, vw, loctypes, parent=None):
        VivView.__init__(self, vw, parent=parent)
        self.loctypes = loctypes

        locs = []
        for ltype in self.loctypes:
            locs.extend( vw.getLocations(ltype) )

        rows = [ ('0x%.8x' % loc[0], vw.reprLocation(loc), loc) for loc in locs ]

        model = VivLocModel(rows=rows)
        self.setModel(model)

    def VWE_ADDLOCATION(self, vw, event, loc):
        lva, lsize, ltype, linfo = loc
        if ltype in self.loctypes:
            self.model().sourceModel().append( ('0x%.8x' % lva, self.vw.reprLocation(loc), loc) )

    def VWE_DELLOCATION(self, vw, event, einfo):
        lva, lsize, ltype, linfo = einfo
        if ltype in self.loctypes:
            print 'DEL ONE!'

def getLocView(vw, loctypes, title, parent=None):
    view = VivLocView( vw, loctypes, parent=parent)
    view.setWindowTitle(title)
    return vw.getVivGui().vqDockWidget( view, floating=True )

class VQVivTreeView(vq_tree.VQTreeView, viv_base.VivEventCore):

    window_title = "VivTreeView"
    _viv_navcol = 0

    def __init__(self, vw, vwqgui):
        vq_tree.VQTreeView.__init__(self, parent=vwqgui)
        viv_base.VivEventCore.__init__(self, vw)

        self.vw = vw
        self.vwqgui = vwqgui
        self._viv_va_nodes = {}

        vwqgui.addEventCore(self)

        self.setWindowTitle(self.window_title)
        self.setSortingEnabled(True)
        self.setDragEnabled( True )

        self.doubleClicked.connect( self.doubleClickedSignal )

    def doubleClickedSignal(self, idx):
        if idx.isValid() and self._viv_navcol != None:
            pnode = idx.internalPointer()
            expr = pnode.rowdata[self._viv_navcol]
            vqtevent('envi:nav:expr', ('viv',expr,None))
            return True

    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(parent=self)
        idxlist = self.selectedIndexes()
        if not idxlist:
            return

        idx = idxlist[0]
        if idx.isValid() and self._viv_navcol != None:
            pnode = idx.internalPointer()
            expr = pnode.rowdata[self._viv_navcol]
            v_q_ctxmenu.buildContextMenu(self.vw, expr=expr, menu=menu)

        menu.exec_(event.globalPos())

    def vivAddRow(self, va, *row):
        node = self.model().append(row)
        node.va = va
        self._viv_va_nodes[va] = node
        return node

    def vivDelRow(self, va):
        node = self._viv_va_nodes.pop(va, None)
        if node:
            self.model().vqDelRow(node)

    def vivSetData(self, va, col, val):
        '''
        Set a row/col in the data model.  This will quietly fail
        if we don't contain a row for the va (makes users not need
        to check...)

        Example: view.vivSetData(0x41414141, 2, 'Woot Function')

        NOTE: This is for use by the VWE_ event callback handlers!
        '''
        pnode = self._viv_va_nodes.get(va)
        if not pnode:
            return

        idx = self.model().createIndex(pnode.row(), col, pnode)
        # We are *not* the edit role...
        self.model().setData(idx, val, role=None)

    def vivGetData(self, va, col):
        pnode = self._viv_va_nodes.get(va)
        if not pnode:
            return None
        return pnode.rowdata[col]

class VQVivLocView(VQVivTreeView):

    loctypes = ()

    def __init__(self, vw, vwqgui):
        VQVivTreeView.__init__(self, vw, vwqgui)
        model = VivNavModel(self._viv_navcol, parent=self, columns=self.columns)
        self.setModel(model)
        self.vqLoad()
        self.vqSizeColumns()

    def vqLoad(self):

        for l in self.loctypes:
            for lva, lsize, ltype, linfo in self.vw.getLocations(l):
                self.vivAddLocation(lva, lsize, ltype, linfo)

    def VWE_DELLOCATION(self, vw, event, einfo):
        lva, lsize, ltype, linfo = einfo
        self.vivDelRow(lva)

    def VWE_ADDLOCATION(self, vw, event, einfo):
        lva, lsize, ltype, linfo = einfo
        if ltype in self.loctypes:
            self.vivAddLocation(lva, lsize, ltype, linfo)

    def vivAddLocation(self, lva, lsize, ltype, linfo):
        print "FIXME OVERRIDE"

class VQVivStringsView(VQVivLocView):

    columns = ('Address','String')
    loctypes = (LOC_STRING, LOC_UNI)
    window_title = 'Strings'

    def vivAddLocation(self, lva, lsize, ltype, linfo):
        s = self.vw.readMemory(lva, lsize)
        if ltype == LOC_UNI:
            s = s.decode('utf-16le', 'ignore')
        self.vivAddRow(lva, '0x%.8x' % lva, repr(s))

class VQVivImportsView(VQVivLocView):

    columns = ('Address', 'Library', 'Function')
    loctypes = (LOC_IMPORT,)
    window_title = 'Imports'

    def vivAddLocation(self, lva, lsize, ltype, linfo):
        libname, funcname = linfo.split('.', 1)
        self.vivAddRow(lva, '0x%.8x' % lva, libname, funcname)

class VQVivStructsView(VQVivLocView):
    columns = ('Address', 'Structure', 'Loc Name')
    loctypes = (LOC_STRUCT,)
    window_title = 'Structures'

    def vivAddLocation(self, lva, lsize, ltype, linfo):
        sym = self.vw.getSymByAddr(lva)
        self.vivAddRow(lva, '0x%.8x' % lva, linfo, str(sym))

class VQVivExportsView(VQVivTreeView):

    window_title = 'Exports'
    columns = ('Address', 'File', 'Export')

    def __init__(self, vw, vwqgui):
        VQVivTreeView.__init__(self, vw, vwqgui)
        self.setModel( VivNavModel(self._viv_navcol, self, columns=self.columns) )
        self.vqLoad()
        self.vqSizeColumns()

    def vqLoad(self):
        for va, etype, ename, fname in self.vw.getExports():
            self.vivAddExport(va, etype, ename, fname)

    def vivAddExport(self, va, etype, ename, fname):
        self.vivAddRow(va, '0x%.8x' % va, fname, ename)

    def VWE_ADDEXPORT(self, vw, event, einfo):
        va, etype, ename, fname = einfo
        self.vivAddExport(va, etype, ename, fname)

class VQVivSegmentsView(VQVivTreeView):

    _viv_navcol = 2
    window_title = 'Segments'
    columns = ('Module','Section', 'Address', 'Size')

    def __init__(self, vw, vwqgui):
        VQVivTreeView.__init__(self, vw, vwqgui)
        self.setModel( VivNavModel(self._viv_navcol, self, columns=self.columns) )
        self.vqLoad()
        self.vqSizeColumns()

    def vqLoad(self):
        for va, size, sname, fname in self.vw.getSegments():
            self.vivAddRow(va, fname, sname, '0x%.8x' % va, str(size))

class VQVivFunctionsView(VQVivTreeView):

    _viv_navcol = 0
    window_title = 'Functions'
    columns = ('Name','Address', 'Size', 'Ref Count')

    def __init__(self, vw, vwqgui):
        VQVivTreeView.__init__(self, vw, vwqgui)
        self.setModel( VivNavModel(self._viv_navcol, self, columns=self.columns) )
        self.vqLoad()
        self.vqSizeColumns()

    def vqLoad(self):
        for fva in self.vw.getFunctions():
            self.vivAddFunction(fva)

    def VWE_ADDFUNCTION(self, vw, event, einfo):
        fva, fmeta = einfo
        self.vivAddFunction(fva)

    def VWE_DELFUNCTION(self, vw, event, efino):
        fva, fmeta = einfo
        self.vivDelRow(fva)

    def VWE_SETNAME(self, vw, event, einfo):
        va, name = einfo
        self.vivSetData(va, 0, name)

    def vivAddFunction(self, fva):

        size   = self.vw.getFunctionMeta(fva, "Size", -1)
        fname  = self.vw.getName(fva)
        xcount = len(self.vw.getXrefsTo(fva))
        self.vivAddRow(fva, fname, '0x%.8x' % fva, size, xcount)

    def VWE_ADDXREF(self, vw, event, einfo):
        fromva, tova, rtype, rflag = einfo
        cnt = self.vivGetData(tova, 3)
        if cnt == None:
            return
        self.vivSetData(tova, 3, cnt + 1)

    def VWE_DELXREF(self, vw, event, einfo):
        fromva, tova, rtype, rflag = einfo
        cnt = self.vivGetData(tova, 3)
        if cnt == None:
            return
        self.vivSetData(tova, 3, cnt - 1)

    def VWE_SETFUNCMETA(self, vw, event, einfo):
        funcva, key, value = einfo
        if key == "Size":
            self.vivSetData(funcva, 2, value)

vaset_coltypes = {
    VASET_STRING:str,
    VASET_ADDRESS:long,
    VASET_INTEGER:long,
}

class VQVivVaSetView(VQVivTreeView):

    _viv_navcol = 0

    def __init__(self, vw, vwqgui, setname):
        self._va_setname = setname

        setdef = vw.getVaSetDef( setname )
        cols = [ cname for (cname,ctype) in setdef ]

        VQVivTreeView.__init__(self, vw, vwqgui)

        self.setModel( VivNavModel(self._viv_navcol, self, columns=cols) )
        self.vqLoad()
        self.vqSizeColumns()
        self.setWindowTitle('Va Set: %s' % setname)

    def VWE_SETVASETROW(self, vw, event, einfo):
        setname, row = einfo
        if setname == self._va_setname:
            va = row[0]
            row = list(row)
            row[0] = '0x%.8x' % va
            self.vivAddRow( va, *row )

    def vqLoad(self):
        setdef = self.vw.getVaSetDef( self._va_setname )
        rows = self.vw.getVaSetRows( self._va_setname )
        for row in rows:
            va = row[0]
            row = list(row)
            row[0] = '0x%.8x' % va
            self.vivAddRow(va, *row)

class VQXrefView(VQVivTreeView):

    _viv_navcol = 0

    def __init__(self, vw, vwqgui, xrefs=(), title='Xrefs'):

        self.window_title = title

        VQVivTreeView.__init__(self, vw, vwqgui)
        model = VivNavModel(self._viv_navcol, self, columns=('Xref From', 'Xref Type', 'Xref Flags', 'Func Name'))
        self.setModel(model)

        for fromva, tova, rtype, rflags in xrefs:
            fva = vw.getFunction(fromva)
            funcname = ''
            if fva:
                funcname = vw.getName(fva)
            self.vivAddRow(fromva, '0x%.8x' % fromva, rtype, rflags, funcname)

        self.vqSizeColumns()

class VQVivNamesView(VQVivTreeView):

    _viv_navcol = 0
    window_title = 'Workspace Names'
    columns = ('Address', 'Name')

    def __init__(self, vw, vwqgui):
        VQVivTreeView.__init__(self, vw, vwqgui)
        self.setModel( VivNavModel(self._viv_navcol, self, columns=self.columns) )
        self.vqLoad()
        self.vqSizeColumns()

    def vqLoad(self):
        for name in self.vw.getNames():
            self.vivAddName(name)

    def VWE_SETNAME(self, vw, event, einfo):
        va, name = einfo
        #self.vivSetData(va, 1, name)
        self.vivAddName(einfo)

    def vivAddName(self, nifo):
        va, name = nifo
        if self.vivGetData(va, 0) == None:
            self.vivAddRow(va, '0x%.8x' % va, name)
        else:
            self.vivSetData(va, 1, name)

