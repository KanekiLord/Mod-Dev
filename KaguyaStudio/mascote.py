"""Pixel art Kaguya: sprite-ready presenter for docked/floating UI.

No external modules, API credentials, background services, or changes to user files.
User-provided PNG sprites take priority; a local pixel placeholder is drawn if absent.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

KEY = '#010203'
BACK = '#101827'
FG = '#F1EDF5'
HAIR = '#DBCDD9'
EXPRESSION_LABELS = {
    'neutra': 'Neutra', 'feliz': 'Feliz', 'sorriso_sutil': 'Sorriso sutil',
    'falando': 'Falando', 'surpresa': 'Surpresa', 'curiosa': 'Curiosa',
    'pensando': 'Pensando', 'confiante': 'Confiante', 'provocante': 'Provocante',
    'apaixonada': 'Apaixonada', 'emburrada': 'Emburrada', 'triste': 'Triste',
    'envergonhada': 'Envergonhada', 'preocupada': 'Preocupada',
    'cansada': 'Cansada', 'chorando': 'Chorando', 'determinada': 'Determinada',
    'rindo': 'Rindo',
}
CLAUDE_EXPRESSION_LABELS = {
    'neutra':'Neutra', 'feliz':'Feliz', 'pensando':'Pensando',
    'falando':'Falando', 'surpresa':'Surpresa', 'piscando':'Piscando',
    'focada':'Focada', 'sucesso':'Sucesso', 'cafe':'Café',
}
PROFILES = {
    'kaguya': {
        'name':'Kaguya', 'agent':'Codex', 'prefix':'kaguya',
        'labels':EXPRESSION_LABELS,
        'fallbacks':{'trabalhando':'determinada'},
        'accent':'#C7A1F7', 'footer':'#21152E',
    },
    'claude': {
        'name':'Claude', 'agent':'Claude Code', 'prefix':'claude_feminina',
        'labels':CLAUDE_EXPRESSION_LABELS,
        'fallbacks':{'trabalhando':'focada', 'preocupada':'surpresa',
                     'determinada':'focada', 'triste':'pensando'},
        'accent':'#FF9A60', 'footer':'#332020',
    },
}
ALLOWED = set(EXPRESSION_LABELS) | {'trabalhando'}
FALLBACKS = PROFILES['kaguya']['fallbacks']

def expression_names(mascot_id: str = 'kaguya') -> tuple[str,...]:
    if mascot_id not in PROFILES:return ()
    return tuple(PROFILES[mascot_id]['labels'])

def label_for_state(state: str, mascot_id: str = 'kaguya') -> str:
    profile=PROFILES.get(mascot_id,PROFILES['kaguya'])
    if state == 'trabalhando':return profile['agent']+' trabalhando'
    return profile['labels'].get(state, 'Neutra')

def state_for_agent_status(agent: str, phase: str) -> str:
    """Status de cada CLI sem inventar progresso ou aprovação de testes."""
    result={
        'codex':{'running':'determinada','success':'feliz','error':'preocupada',
                 'cancelled':'preocupada','idle':'neutra'},
        'claude':{'running':'focada','success':'sucesso','error':'surpresa',
                  'cancelled':'pensando','idle':'neutra'},
    }
    return result.get(agent,{}).get(phase,'neutra')

@dataclass
class MascotSettings:
    visible: bool = True
    x: int = -1
    y: int = -1
    topmost: bool = True
    scale: int = 2
    animations: bool = False  # frames supplied from reference are not yet production-grade
    @classmethod
    def load(cls, path: Path):
        try:
            raw=json.loads(path.read_text(encoding='utf-8'))
            allowed={k:raw[k] for k in asdict(cls()).keys() if k in raw}
            obj=cls(**allowed)
            if not isinstance(obj.visible,bool) or not isinstance(obj.topmost,bool):raise ValueError('Booleans inválidos')
            if not isinstance(obj.x,int) or not isinstance(obj.y,int):raise ValueError('Posição inválida')
            if obj.scale not in (1,2,3):raise ValueError('Escala inválida')
            if not isinstance(obj.animations,bool):raise ValueError('Animação inválida')
            return obj
        except (OSError,ValueError,TypeError,KeyError):
            return cls()
    def save(self, path: Path):
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(asdict(self),ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,path)

def state_for_status(message: str) -> str:
    s=message.lower()
    if any(word in s for word in ('erro','falhou','interromp','cancelad')):return 'preocupada'
    if 'executad' in s and 'executando' not in s:return 'feliz'
    if any(word in s for word in ('executando','iniciando','processando')):return 'trabalhando'
    return 'neutra'

def sprite_path(base:Path, state:str, mascot_id:str='kaguya') -> Path|None:
    profile=PROFILES.get(mascot_id)
    if profile is None:return None
    labels=profile['labels']
    if state not in labels and state not in profile['fallbacks'] and state!='trabalhando':return None
    for label in (state,profile['fallbacks'].get(state),'neutra'):
        if label in labels:
            path=base/'expressoes'/f"{profile['prefix']}_{label}.png"
            if path.is_file():return path
    return None

def animation_sprite(base:Path,state:str,tick:int,animations:bool=True,mascot_id:str='kaguya')->Path|None:
    """Claude atualmente tem expressões estáticas; a Kaguya possui frames opcionais."""
    if mascot_id!='kaguya' or not animations:
        return sprite_path(base,state,mascot_id)
    folder=base/'animacoes'
    seq=None;index=1
    if state=='falando':
        seq='talk';index=(tick//3)%3+1
    elif state == 'neutra':
        if 48 <= tick%58 < 51:
            seq='blink';index=tick%58-47
        else:
            seq='idle';index=(tick//6)%4+1
    if seq:
        candidate=folder/f'{seq}_{index:02d}.png'
        if candidate.is_file():return candidate
    return sprite_path(base,state,mascot_id)

def safe_location(x:int,y:int,sw:int,sh:int,w:int,h:int)->tuple[int,int]:
    return max(0,min(x,max(0,sw-w))),max(0,min(y,max(0,sh-h)))


def draw_pixel_kaguya(c:tk.Canvas,w:int,h:int,state:str='neutra', bob:int=0):
    """Fallback sprite drawn on Canvas; actual user sprites always override it."""
    c.delete('all')
    tile=max(1,min(w//46,h//58))
    ox=(w-46*tile)//2;oy=(h-58*tile)//2 + bob
    def r(x1,y1,x2,y2,col):
        c.create_rectangle(ox+x1*tile,oy+y1*tile,ox+x2*tile,oy+y2*tile,fill=col,outline='')
    # long flowing silver-violet hair and outline
    dark='#685675';shade='#9B83A2'; light='#FBEDF4'; violet='#C0A7C7'
    skin='#F4C3B4';shadskin='#E3A394'; eye='#923757';eyes='#F7F1EA'; gold='#E8B976'
    r(10,8,36,53,dark); r(7,18,40,55,dark); r(12,4,33,46,shade)
    r(9,12,37,52,violet);r(8,29,14,54,shade);r(33,26,39,55,shade)
    r(14,9,32,30,skin);r(15,24,32,32,shadskin);r(17,26,30,37,skin)
    # hair fringe cascading across forehead
    r(12,4,31,12,light);r(9,10,18,20,light);r(28,9,36,21,violet)
    r(11,11,15,25,shade);r(13,12,16,20,light)
    r(19,7,33,10,violet);r(24,10,32,14,light)
    # earrings
    r(10,26,12,32,gold);r(35,25,37,31,gold)
    # eyes and brows/expressions
    if state in ('feliz',):
        r(17,22,21,23,eye);r(26,22,30,23,eye)
        r(17,23,19,24,eye);r(28,23,30,24,eye)
    elif state in ('preocupada',):
        r(17,19,21,20,dark);r(26,20,30,21,dark)
        r(17,22,22,24,eyes);r(26,22,31,24,eyes)
        r(19,22,21,25,eye);r(28,22,30,25,eye)
    else:
        r(17,21,22,24,eyes);r(26,21,31,24,eyes)
        r(19,21,21,25,eye);r(28,21,30,25,eye)
        r(19,22,20,23,'#FFFFFF');r(28,22,29,23,'#FFFFFF')
    # lips
    if state=='falando':r(23,28,27,31,eye)
    elif state=='feliz':r(22,28,28,30,eye);r(23,28,27,29,skin)
    elif state=='preocupada':r(23,30,27,31,eye)
    else:r(23,29,27,30,eye)
    # outfit: white/lilac dress, golden embellishments
    r(11,38,37,57,dark);r(12,39,36,57,light)
    r(16,38,32,45,skin);r(17,44,31,55,violet)
    r(12,40,18,57,'#F8EEF2');r(31,40,36,57,'#F8EEF2')
    r(20,42,28,44,gold);r(23,43,25,47,'#AA75BE')
    r(17,52,33,54,gold);r(14,47,17,49,gold);r(33,47,35,49,gold)
    if state=='pensando':r(35,31,39,35,skin);r(33,33,36,40,skin)
    if state=='surpresa':r(23,27,27,32,eye)


class MascotPresenter:
    def __init__(self, app:tk.Tk, root_dir:Path, pref_path:Path, on_chat, on_open, mascot_id:str="kaguya"):
        self.app=app;self.root_dir=Path(root_dir);self.pref_path=Path(pref_path)
        if mascot_id not in PROFILES:raise ValueError("Mascote desconhecida")
        self.mascot_id=mascot_id;self.profile=PROFILES[mascot_id]
        self.settings=MascotSettings.load(pref_path)
        self.state='neutra';self.tick=0;self.window=None;self.dock=None;self.quick=None
        self._images={};self._image_refs=[];self._drag=None
        self.on_chat=on_chat;self.on_open=on_open
        self.settings.scale=max(1,min(self.settings.scale,3))
    def attach_dock(self, canvas:tk.Canvas):
        self.dock=canvas
        self._render_one(canvas, canvas.winfo_reqwidth(),canvas.winfo_reqheight())
        canvas.bind('<Double-Button-1>',lambda e:self.open_quick_chat())
        canvas.bind('<Button-3>',lambda e:self._show_menu(e))
    def _photo(self,path:Path,w:int,h:int):
        """Nearest-neighbor integer scaling and cached Tk images (no Pillow needed)."""
        try:
            stamp=path.stat().st_mtime_ns
            key=(str(path),stamp,w,h)
            if key in self._images:
                return self._images[key]
            original=tk.PhotoImage(file=str(path),master=self.app)
            ow,oh=original.width(),original.height()
            if ow>w or oh>h:
                import math
                n=max(1,math.ceil(max(ow/max(w,1),oh/max(h,1))))
                img=original.subsample(n,n)
            else:
                n=max(1,int(min(w/max(ow,1),h/max(oh,1))))
                img=original.zoom(n,n) if n>1 else original
            if len(self._images)>100:
                self._images.clear()
            self._images[key]=img
            return img
        except (tk.TclError,OSError,ValueError):return None
    def _render_one(self,canvas:tk.Canvas,w:int,h:int):
        canvas.delete('all')
        path=animation_sprite(self.root_dir,self.state,self.tick,self.settings.animations,self.mascot_id)
        img=self._photo(path,w,h) if path else None
        if img:
            self._image_refs.append(img)
            self._image_refs=self._image_refs[-12:]
            canvas.create_image(w//2,h//2,image=img,anchor='center')
        else:draw_pixel_kaguya(canvas,w,h,self.state,bob=(1 if self.tick%12>=7 else 0))
    def redraw(self):
        if self.dock and self.dock.winfo_exists():
            self._render_one(self.dock,self.dock.winfo_width() or 90,self.dock.winfo_height() or 108)
        if self.window and self.window.winfo_exists():
            self._render_float()
    def set_state(self,state:str):
        new=state if (state in self.profile['labels'] or state in self.profile['fallbacks']) else 'neutra'
        if self.state!=new:
            self.state=new
            self.redraw()
    def animate(self):
        self.tick+=1
        if self.settings.animations and self.tick%1==0:self.redraw()
        self._timer=self.app.after(220,self.animate)
    def _size(self):
        # 128-pixel originals at an integer scale; 32px footer sits below the image.
        return (128*self.settings.scale,128*self.settings.scale+32)
    def show(self):
        self.settings.visible=True
        if self.window and self.window.winfo_exists():
            self.window.deiconify();self.window.lift()
        else:self._make_window()
        self.settings.save(self.pref_path)
    def hide(self):
        self.settings.visible=False
        if self.window and self.window.winfo_exists():self.window.withdraw()
        self.settings.save(self.pref_path)
        if getattr(self.app,'only_mascot',False):
            mascots=getattr(self.app,'mascots',[self])
            if not any(m.settings.visible for m in mascots):self.app._close()
    def toggle(self):
        if self.settings.visible:self.hide()
        else:self.show()
    def _make_window(self):
        w,h=self._size()
        self.window=tk.Toplevel(self.app)
        self.window.title(self.profile['name']+' — mascote do '+self.profile['agent'])
        self.window.configure(bg=KEY)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost',self.settings.topmost)
        if os.name=='nt':
            try:self.window.wm_attributes('-transparentcolor',KEY)
            except tk.TclError:pass
        self.canvas=tk.Canvas(self.window,width=w,height=h,highlightthickness=0,bd=0,bg=KEY)
        self.canvas.pack()
        sw=self.window.winfo_screenwidth();sh=self.window.winfo_screenheight()
        if self.settings.x<0 or self.settings.y<0:
            self.settings.x=sw-w-75 if self.mascot_id=='kaguya' else sw-2*w-110
            self.settings.y=sh-h-100
        self.settings.x,self.settings.y=safe_location(self.settings.x,self.settings.y,sw,sh,w,h)
        self.window.geometry(f'{w}x{h}+{self.settings.x}+{self.settings.y}')
        self.window.bind('<ButtonPress-1>',self._drag_start)
        self.window.bind('<B1-Motion>',self._drag_move)
        self.window.bind('<ButtonRelease-1>',self._drag_end)
        self.window.bind('<Double-Button-1>',lambda e:self.open_quick_chat())
        self.window.bind('<Button-3>',self._show_menu)
        self.window.protocol('WM_DELETE_WINDOW',self.hide)
        self._render_float()
    def _render_float(self):
        if not (self.window and self.window.winfo_exists()):return
        w,h=self._size();self._render_one(self.canvas,w,h-32)
        # transparent background on Windows; footer is intentionally visible
        self.canvas.create_rectangle(12,h-30,w-12,h-5,fill=self.profile['footer'],outline=self.profile['accent'],width=1)
        label=label_for_state(self.state,self.mascot_id)
        self.canvas.create_text(w//2,h-18,text=self.profile['name'].upper()+'  •  '+label,fill=FG,font=('Segoe UI',8,'bold'))
    def _drag_start(self,e):
        self._drag=(e.x_root,e.y_root,self.settings.x,self.settings.y)
    def _drag_move(self,e):
        if self._drag is None:return
        ox,oy,sx,sy=self._drag
        w,h=self._size()
        self.settings.x,self.settings.y=safe_location(sx+e.x_root-ox,sy+e.y_root-oy,
            self.window.winfo_screenwidth(),self.window.winfo_screenheight(),w,h)
        self.window.geometry(f'+{self.settings.x}+{self.settings.y}')
    def _drag_end(self,e):
        self._drag=None;self.settings.save(self.pref_path)
    def _show_menu(self,e):
        menu=tk.Menu(self.app,tearoff=0,bg='#182338',fg=FG,activebackground='#334763',activeforeground=FG)
        menu.add_command(label='Chat rápido',command=self.open_quick_chat)
        menu.add_command(label='Abrir Kaguya Studio',command=self.on_open)
        menu.add_separator()
        menu.add_command(label='Sempre visível: '+('ligado' if self.settings.topmost else 'desligado'),command=self.toggle_topmost)
        menu.add_command(label='Tamanho maior',command=lambda:self.resize(1))
        menu.add_command(label='Tamanho menor',command=lambda:self.resize(-1))
        menu.add_command(label='Animações de teste: '+('ligadas' if self.settings.animations else 'desligadas'),
                         command=self.toggle_animations)
        expressions=tk.Menu(menu,tearoff=0,bg='#182338',fg=FG,activebackground='#334763',activeforeground=FG)
        for state,label in self.profile['labels'].items():
            expressions.add_command(label=label,command=lambda chosen=state:self.set_state(chosen))
        menu.add_cascade(label=f"Expressões ({len(self.profile['labels'])})",menu=expressions)
        menu.add_separator()
        menu.add_command(label='Fechar mascote' if getattr(self.app,'only_mascot',False)
                         else 'Ocultar mascote',command=self.hide)
        menu.tk_popup(e.x_root,e.y_root)
        menu.grab_release()
    def toggle_animations(self):
        self.settings.animations=not self.settings.animations
        self.settings.save(self.pref_path)
        self.redraw()
    def toggle_topmost(self):
        self.settings.topmost=not self.settings.topmost
        if self.window and self.window.winfo_exists():self.window.attributes('-topmost',self.settings.topmost)
        self.settings.save(self.pref_path)
    def resize(self,increment):
        self.settings.scale=max(1,min(3,self.settings.scale+increment))
        if self.window and self.window.winfo_exists():
            w,h=self._size()
            self.canvas.config(width=w,height=h)
            self.settings.x,self.settings.y=safe_location(self.settings.x,self.settings.y,
                self.window.winfo_screenwidth(),self.window.winfo_screenheight(),w,h)
            self.window.geometry(f'{w}x{h}+{self.settings.x}+{self.settings.y}')
            self.redraw()
        self.settings.save(self.pref_path)
    def open_quick_chat(self):
        if self.quick and self.quick.winfo_exists():self.quick.lift();self.quick.focus_force();return
        self.quick=tk.Toplevel(self.app)
        self.quick.title('Falar com Codex e Claude — '+self.profile['name'])
        self.quick.geometry('460x265')
        self.quick.configure(bg=BACK)
        self.quick.attributes('-topmost',True)
        ttk.Label(self.quick,text='Mensagem rápida • sem interromper tarefas ativas').pack(padx=14,pady=(12,5),anchor='w')
        self.quick_target=tk.StringVar(value='Claude' if self.mascot_id=='claude' else 'Codex')
        selector=ttk.Combobox(self.quick,state='readonly',values=['Equipe','Codex','Claude'],textvariable=self.quick_target)
        selector.pack(fill='x',padx=14)
        entry=tk.Text(self.quick,height=5,wrap='word',bg='#253148',fg=FG,insertbackground=FG)
        entry.pack(fill='both',expand=True,padx=14,pady=8)
        bar=ttk.Frame(self.quick);bar.pack(fill='x',padx=14,pady=(0,12))
        def send(kind=None):
            raw=entry.get('1.0','end').strip()
            if not raw:return
            if self.on_chat(raw,self.quick_target.get(),kind):
                entry.delete('1.0','end')
                self.quick.lift()
        ttk.Button(bar,text='Enviar',command=send).pack(side='left',padx=3)
        ttk.Button(bar,text='Guardar para depois',command=lambda:send('DEPOIS')).pack(side='left',padx=3)
        ttk.Button(bar,text='Registrar ideia',command=lambda:send('IDEIA')).pack(side='left',padx=3)
        entry.bind('<Control-Return>',lambda e:send())
        entry.focus_set()
    def close(self):
        if hasattr(self,'_timer'):
            try:self.app.after_cancel(self._timer)
            except tk.TclError:pass
            del self._timer
        if self.window and self.window.winfo_exists():self.window.destroy()
        if self.quick and self.quick.winfo_exists():self.quick.destroy()
