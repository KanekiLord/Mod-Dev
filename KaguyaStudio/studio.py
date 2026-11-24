#!/usr/bin/env python3
"""Kaguya Studio V3: Windows GUI, no extra services or API keys."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

from core import Store, Vault, classify_message, inventory, minimal_context
from runtime import run_cli, run_quality, check_project_writable, Cancelled, check_subscription
from diagnostico import export_report
from mascote import MascotPresenter, state_for_status, state_for_agent_status

ROOT=Path(__file__).resolve().parent
HOME=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.kaguya-studio')))/'KaguyaStudioV3'
CATALOG=ROOT/'catalogo'/'agentes.json'
BG='#100B1B'; SURFACE='#1E162D'; PANEL='#2A1D3B'; FG='#F8EFF7'; MUTED='#AFA3C1'
BLUE='#C09CF9'; ORANGE='#E8AA7F'; GREEN='#72D8AB'; RED='#EF859B'; GOLD='#F2C99F'; BORDER='#433152'


class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Kaguya Studio V3.4 — Codex + Claude Code + Obsidian')
        self.geometry('1480x900'); self.minsize(1110,710)
        self.configure(background=BG)
        HOME.mkdir(parents=True,exist_ok=True)
        self.store=Store(HOME/'studio.sqlite3')
        self.store.recover_interrupted()
        self.events=queue.Queue()
        self.current_cancel=None
        self.worker=None
        self.pid=None
        self.last_output=''
        self.mascot=MascotPresenter(self,ROOT/'mascotes'/'kaguya',HOME/'mascote.json',
                                    self._quick_message,self._show_studio)
        self.claude_mascot=MascotPresenter(self,ROOT/'mascotes'/'claude',
            HOME/'mascote_claude.json',self._quick_message,self._show_studio,mascot_id='claude')
        self.mascots=[self.mascot,self.claude_mascot]
        self._style()
        self._build()
        self._load_projects()
        for mascot in self.mascots:
            if mascot.settings.visible:mascot.show()
            mascot.animate()
        self._poll_timer=self.after(170,self._poll)
        self.protocol('WM_DELETE_WINDOW',self._close)

    def _style(self):
        s=ttk.Style(self)
        s.theme_use('clam')
        s.configure('.',background=BG,foreground=FG,font=('Segoe UI',10))
        s.configure('TFrame',background=BG)
        s.configure('Panel.TFrame',background=SURFACE)
        s.configure('TLabel',background=BG,foreground=FG)
        s.configure('Muted.TLabel',background=BG,foreground=MUTED)
        s.configure('Title.TLabel',background=BG,foreground=FG,font=('Segoe UI Semibold',17))
        s.configure('TButton',background=PANEL,foreground=FG,padding=(13,9),borderwidth=0,
                    font=('Segoe UI Semibold',9))
        s.map('TButton',background=[('active','#49345D'),('pressed','#583A6E')])
        s.configure('Primary.TButton',background='#744493',foreground='#FFF5FA',padding=(17,10))
        s.map('Primary.TButton',background=[('active','#8C57AF')])
        s.configure('TCombobox',fieldbackground=PANEL,background=PANEL,foreground=FG,
                    arrowcolor=GOLD,borderwidth=0,padding=(7,6))
        s.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',FG)])
        s.configure('TCheckbutton',background=BG,foreground=FG)
        s.map('TCheckbutton',background=[('active',BG)])
        s.configure('TEntry',fieldbackground=PANEL,foreground=FG,padding=8)
        s.configure('TNotebook',background=BG,borderwidth=0,tabmargins=(0,4,0,0))
        s.configure('TNotebook.Tab',background=SURFACE,foreground=MUTED,padding=(18,12),
                    font=('Segoe UI Semibold',9),borderwidth=0,relief='flat',lightcolor=BG,darkcolor=BG,bordercolor=BG)
        s.map('TNotebook.Tab',background=[('selected','#55336D'),('active','#342445')],
              foreground=[('selected','#FFF1FE'),('active',FG)])
        s.configure('Treeview',background=SURFACE,fieldbackground=SURFACE,foreground=FG,
                    rowheight=33,borderwidth=0,font=('Segoe UI',9))
        s.configure('Treeview.Heading',background=PANEL,foreground=GOLD,padding=9,
                    font=('Segoe UI Semibold',9))
        s.map('Treeview',background=[('selected','#624278')])

    def _nav_to(self,tab):
        self.tabs.select(tab)
        self._refresh_nav()

    def _refresh_nav(self,event=None):
        if not hasattr(self,'nav_buttons'):return
        current=self.tabs.select()
        for tab,button in self.nav_buttons.items():
            active=str(tab)==str(current)
            button.configure(bg='#603776' if active else '#181124',
                             fg='#FFF2F8' if active else '#C6B6D1',
                             activebackground='#71428C')

    def _refresh_sidebar_projects(self):
        if not hasattr(self,'sidebar_projects'):return
        for child in self.sidebar_projects.winfo_children():child.destroy()
        for index,project in enumerate(getattr(self,'projects',[])[:8]):
            selected=project['id']==self.pid
            text='◉  '+project['name']
            tk.Button(self.sidebar_projects,text=text,anchor='w',relief='flat',bd=0,highlightthickness=0,
                fg=GOLD if selected else '#CFC3DB',bg='#30203F' if selected else '#181124',
                activebackground='#4D315F',activeforeground=FG,
                padx=14,pady=9,font=('Segoe UI',9),cursor='hand2',
                command=lambda i=index:self._sidebar_select_project(i)).pack(fill='x',pady=2)
        if not getattr(self,'projects',[]):
            tk.Label(self.sidebar_projects,text='Nenhum projeto vinculado',bg='#181124',
                     fg=MUTED,font=('Segoe UI',9),wraplength=176).pack(anchor='w',padx=11,pady=7)

    def _sidebar_select_project(self,index):
        self.project_combo.current(index)
        self._project_selected()

    def _update_right_panel(self):
        if not hasattr(self,'metric_project'):return
        if self.pid is None:
            self.metric_project.set('Selecione um projeto')
            self.metric_tasks.set('0')
            self.metric_vault.set('Não vinculado')
            return
        try:
            project=self.store.project(self.pid)
            tasks=self.store.tasks(self.pid)
            self.metric_project.set(project['name'])
            self.metric_tasks.set(str(len([t for t in tasks if t['status'] in ('queued','running','parked')])))
            self.metric_vault.set('Vinculado' if Path(project['vault']).is_dir() else 'Pasta indisponível')
        except Exception:
            self.metric_project.set('Projeto indisponível')

    def _build(self):
        # Banner uses original generated visual art, while all buttons/text remain native Tk widgets.
        banner=tk.Canvas(self,height=82,highlightthickness=0,bd=0,bg='#140e20')
        banner.pack(side='top',fill='x')
        banner.pack_propagate(False)
        art=ROOT/'assets'/'cabecalho_sakura.png'
        self._banner_image=None
        if art.is_file():
            try:
                self._banner_image=tk.PhotoImage(file=str(art),master=self)
                banner.create_image(0,0,image=self._banner_image,anchor='nw')
            except tk.TclError:pass
        banner.create_text(28,25,text='☾  KAGUYA STUDIO',anchor='w',
              fill=GOLD,font=('Georgia',22,'bold'))
        banner.create_text(31,58,text='CODEX  ·  CLAUDE CODE  ·  OBSIDIAN',anchor='w',
              fill='#D0B9E0',font=('Segoe UI',9))
        banner.create_text(510,27,text='V3.4',anchor='w',fill='#E3C1EC',font=('Segoe UI Semibold',11))

        body=tk.Frame(self,bg=BG)
        body.pack(fill='both',expand=True)

        # Compact navigation: routes to the existing functional tabs.
        left=tk.Frame(body,bg='#181124',width=218,highlightthickness=1,
                      highlightbackground='#34243C')
        left.pack(side='left',fill='y');left.pack_propagate(False)
        tk.Label(left,text='ESPAÇO DE TRABALHO',bg='#181124',fg='#AC91BD',
                 font=('Segoe UI Semibold',9)).pack(anchor='w',padx=16,pady=(24,10))
        self.sidebar_nav=tk.Frame(left,bg='#181124')
        self.sidebar_nav.pack(fill='x',padx=8)
        self.nav_buttons={}
        tk.Label(left,text='PROJETOS',bg='#181124',fg='#AC91BD',
                 font=('Segoe UI Semibold',9)).pack(anchor='w',padx=16,pady=(33,10))
        self.sidebar_projects=tk.Frame(left,bg='#181124')
        self.sidebar_projects.pack(fill='x',padx=8)
        tk.Button(left,text='+  Vincular projeto',command=self._add_project,
                  bg='#2D1B3D',fg=GOLD,bd=0,relief='flat',highlightthickness=0,activebackground='#4B2C61',
                  activeforeground=FG,font=('Segoe UI Semibold',9),pady=12,cursor='hand2').pack(
                  side='bottom',fill='x',padx=12,pady=16)

        right=tk.Frame(body,bg='#171023',width=342,
                       highlightbackground='#34243C',highlightthickness=1)
        right.pack(side='right',fill='y');right.pack_propagate(False)
        # Distinct genuine PNG sprites from the user: each assistant has its own dock.
        duo=tk.Frame(right,bg='#171023')
        duo.pack(fill='x',padx=9,pady=(12,7))
        self.codex_state_label=tk.StringVar(value='Aguardando tarefa')
        self.claude_state_label=tk.StringVar(value='Aguardando tarefa')
        for idx, (mascot, agent_name, subtitle, accent, variable) in enumerate((
                (self.mascot,'KAGUYA','CODEX','#C7A1F7',self.codex_state_label),
                (self.claude_mascot,'CLAUDE','CLAUDE CODE','#FF9A60',self.claude_state_label))):
            card=tk.Frame(duo,bg='#21152E' if idx==0 else '#281C26',
                          highlightbackground='#67497B' if idx==0 else '#87523B',
                          highlightthickness=1,width=152,height=230)
            card.pack(side='left',padx=3,fill='x',expand=True)
            card.pack_propagate(False)
            canvas=tk.Canvas(card,width=142,height=144,bg='#21152E' if idx==0 else '#281C26',
                             highlightthickness=0,bd=0)
            canvas.pack(pady=(6,0))
            mascot.attach_dock(canvas)
            if idx==0:self.codex_canvas=canvas
            else:self.claude_canvas=canvas
            tk.Label(card,text=agent_name,bg=card['bg'],fg=accent,
                     font=('Georgia',11,'bold')).pack(pady=(2,0))
            tk.Label(card,text=subtitle,bg=card['bg'],fg='#CFC1D6',
                     font=('Segoe UI Semibold',8)).pack()
            tk.Label(card,textvariable=variable,bg=card['bg'],fg=MUTED,
                     font=('Segoe UI',8)).pack()
            # Clicking the sprite opens the corresponding assistant's quick chat.
            canvas.bind('<Double-Button-1>',lambda e,m=mascot:m.open_quick_chat())
        tk.Label(right,text='STATUS DOS AGENTES',bg='#171023',fg='#B49CC6',
                 font=('Segoe UI Semibold',9)).pack(anchor='w',padx=17,pady=(12,8))
        for icon,name,detail,color in [('◈','Codex','Implementação e testes',BLUE),
                                       ('✧','Claude','Revisão e pesquisa',ORANGE)]:
            card=tk.Frame(right,bg=SURFACE,highlightbackground='#3D2B4A',highlightthickness=1)
            card.pack(fill='x',padx=12,pady=4)
            tk.Label(card,text=icon,bg=SURFACE,fg=color,font=('Segoe UI',20)).pack(side='left',padx=(14,10),pady=9)
            info=tk.Frame(card,bg=SURFACE);info.pack(side='left')
            tk.Label(info,text=name,bg=SURFACE,fg=FG,font=('Segoe UI Semibold',11)).pack(anchor='w')
            tk.Label(info,text=detail,bg=SURFACE,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w')
        tk.Label(right,text='SEGUNDO CÉREBRO',bg='#171023',fg='#B49CC6',
                 font=('Segoe UI Semibold',9)).pack(anchor='w',padx=17,pady=(18,8))
        stat=tk.Frame(right,bg=SURFACE,highlightthickness=1,highlightbackground='#3D2B4A')
        stat.pack(fill='x',padx=12)
        self.metric_vault=tk.StringVar(value='Não vinculado')
        self.metric_tasks=tk.StringVar(value='0')
        self.metric_project=tk.StringVar(value='Selecione um projeto')
        self.metric_agents=tk.StringVar(value='72 catalogados')
        for label,variable in (('Obsidian',self.metric_vault),('Pendentes',self.metric_tasks),
                               ('Agentes',self.metric_agents)):
            row=tk.Frame(stat,bg=SURFACE)
            row.pack(fill='x',padx=12,pady=8)
            tk.Label(row,text=label,bg=SURFACE,fg=MUTED,font=('Segoe UI',9)).pack(side='left')
            tk.Label(row,textvariable=variable,bg=SURFACE,fg=GOLD,font=('Segoe UI Semibold',9)).pack(side='right')
        float_actions=tk.Frame(right,bg='#171023')
        float_actions.pack(side='bottom',fill='x',padx=12,pady=13)
        tk.Button(float_actions,text='☾  Kaguya flutuante',command=self._toggle_float,
                  bg='#3D2751',fg=FG,bd=0,relief='flat',highlightthickness=0,pady=10,
                  font=('Segoe UI Semibold',9),cursor='hand2').pack(fill='x',pady=(0,5))
        tk.Button(float_actions,text='✦  Claude flutuante',command=self._toggle_claude_float,
                  bg='#563326',fg=FG,bd=0,relief='flat',highlightthickness=0,pady=10,
                  font=('Segoe UI Semibold',9),cursor='hand2').pack(fill='x')
        self.float_label=tk.StringVar(value='Ocultar Kaguya' if self.mascot.settings.visible else 'Mostrar Kaguya')

        # Main content retains the existing event handling and tabs.
        center=tk.Frame(body,bg=BG)
        center.pack(side='left',fill='both',expand=True,padx=14,pady=(13,12))
        project=tk.Frame(center,bg=SURFACE,highlightthickness=1,highlightbackground='#3B2B49')
        project.pack(fill='x',pady=(0,10))
        header=tk.Frame(project,bg=SURFACE);header.pack(fill='x',padx=16,pady=(11,4))
        tk.Label(header,text='PROJETO ATUAL',bg=SURFACE,fg='#AF9EC2',
                 font=('Segoe UI Semibold',9)).pack(side='left')
        self.status=tk.StringVar(value='Pronto • sem tarefas em execução')
        tk.Label(header,textvariable=self.status,bg=SURFACE,fg=GREEN,
                 font=('Segoe UI',9),wraplength=290).pack(side='right')
        commands=tk.Frame(project,bg=SURFACE);commands.pack(fill='x',padx=14,pady=(0,12))
        self.project_names=[]
        self.project_combo=ttk.Combobox(commands,state='readonly',width=32)
        self.project_combo.pack(side='left',padx=(0,9))
        self.project_combo.bind('<<ComboboxSelected>>',self._project_selected)
        ttk.Button(commands,text='+ Projeto',command=self._add_project).pack(side='left',padx=3)
        ttk.Button(commands,text='Verificar CLIs',command=self._check_clis).pack(side='left',padx=3)
        ttk.Button(commands,text='Atualizar agentes',command=self._show_inventory).pack(side='left',padx=3)

        self.tabs=ttk.Notebook(center)
        self.tabs.pack(expand=True,fill='both',pady=(0,0))
        self.tab_chat=ttk.Frame(self.tabs,padding=(10,12))
        self.tab_queue=ttk.Frame(self.tabs,padding=(10,12))
        self.tab_memory=ttk.Frame(self.tabs,padding=(10,12))
        self.tab_agents=ttk.Frame(self.tabs,padding=(10,12))
        self.tab_diag=ttk.Frame(self.tabs,padding=(10,12))
        items=[(self.tab_chat,'Conversar','◉  Conversar'),
               (self.tab_queue,'Fila de tarefas','☷  Fila de tarefas'),
               (self.tab_memory,'Segundo Cérebro','◇  Segundo Cérebro'),
               (self.tab_agents,'Agentes e skills','♧  Agentes e skills'),
               (self.tab_diag,'Diagnóstico','⌁  Diagnóstico')]
        for tab,label,nav_label in items:
            self.tabs.add(tab,text=label)
            self.nav_buttons[tab]=tk.Button(self.sidebar_nav,text=nav_label,anchor='w',
                  font=('Segoe UI Semibold',10),bg='#181124',fg='#C6B6D1',
                  activebackground='#71428C',activeforeground=FG,
                  bd=0,relief='flat',highlightthickness=0,padx=15,pady=12,cursor='hand2',
                  command=lambda t=tab:self._nav_to(t))
            self.nav_buttons[tab].pack(fill='x',pady=3)
        self.tabs.bind('<<NotebookTabChanged>>',self._refresh_nav)
        self._build_chat();self._build_queue();self._build_memory();self._build_agents();self._build_diag()
        self._refresh_nav()
        self._refresh_sidebar_projects()
        self._update_right_panel()

    def _avatar(self,parent,title,color):
        frame=ttk.Frame(parent,padding=(0,0,12,0));frame.pack(side='left')
        c=tk.Canvas(frame,width=66,height=61,bg=BG,highlightthickness=0)
        c.pack(side='left')
        c.create_oval(7,5,58,57,fill=PANEL,outline=color,width=2)
        c.create_rectangle(19,20,47,42,fill=color,outline='',width=0)
        c.create_rectangle(22,23,44,39,fill=PANEL,outline='')
        c.create_oval(26,28,30,32,fill=color,outline='')
        c.create_oval(37,28,41,32,fill=color,outline='')
        c.create_line(29,36,38,36,fill=color,width=2)
        c.create_line(32,14,32,20,fill=color,width=2)
        c.create_oval(29,10,35,16,fill=color,outline='')
        ttk.Label(frame,text=title,foreground=color).pack(side='left')
        return c

    def _toggle_float(self):
        self.mascot.toggle()
        self.float_label.set('Ocultar Kaguya' if self.mascot.settings.visible else 'Mostrar Kaguya')

    def _toggle_claude_float(self):
        self.claude_mascot.toggle()

    def _show_studio(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.tabs.select(self.tab_chat)

    def _quick_message(self,raw:str,target:str,forced:str|None):
        route={'Equipe':'equipe','Codex':'codex','Claude':'claude'}.get(target,'equipe')
        return self._submit_message(raw,forced,route,from_quick=True)

    def _build_chat(self):
        self.chat=scrolledtext.ScrolledText(self.tab_chat,wrap='word',font=('Segoe UI',10),
            bg=SURFACE,fg=FG,insertbackground=FG,relief='flat',padx=18,pady=17,height=13,state='disabled')
        self.chat.pack(expand=True,fill='both')
        self.chat.tag_configure('user',foreground='#D3B3FF',font=('Segoe UI Semibold',10),spacing1=12)
        self.chat.tag_configure('codex',foreground=BLUE,font=('Segoe UI Semibold',10),spacing1=12)
        self.chat.tag_configure('claude',foreground=ORANGE,font=('Segoe UI Semibold',10),spacing1=12)
        self.chat.tag_configure('warning',foreground=RED,font=('Segoe UI Semibold',10),spacing1=12)
        self.chat.tag_configure('system',foreground=GREEN,font=('Segoe UI Semibold',10),spacing1=12)
        self.chat.tag_configure('body',foreground='#F0EAF6',lmargin1=5,lmargin2=5,spacing3=10)
        options=ttk.Frame(self.tab_chat);options.pack(fill='x',pady=(9,4))
        ttk.Label(options,text='Destino').pack(side='left')
        self.target=tk.StringVar(value='Equipe (Codex + Claude)')
        self.target_combo=ttk.Combobox(options,state='readonly',width=26,
                                      textvariable=self.target,values=['Equipe (Codex + Claude)','Codex','Claude'])
        self.target_combo.pack(side='left',padx=8)
        self.allow_write=tk.BooleanVar(value=False)
        ttk.Checkbutton(options,text='Permitir alterações (Git)',variable=self.allow_write).pack(side='left',padx=9)
        self.allow_web=tk.BooleanVar(value=True)
        ttk.Checkbutton(options,text='Permitir pesquisa web',variable=self.allow_web).pack(side='left',padx=9)
        self.entry=tk.Text(self.tab_chat,height=4,wrap='word',bg=PANEL,fg=FG,
                           insertbackground=FG,relief='flat',font=('Segoe UI',11),padx=11,pady=10)
        self.entry.pack(fill='x')
        self.entry.bind('<Control-Return>',lambda e:self._send())
        buttons=ttk.Frame(self.tab_chat);buttons.pack(fill='x',pady=(8,0))
        ttk.Button(buttons,text='Enviar  ↗  (Ctrl+Enter)',style='Primary.TButton',command=self._send).pack(side='left',padx=(0,6))
        ttk.Button(buttons,text='Guardar para depois',command=lambda:self._send('DEPOIS')).pack(side='left',padx=3)
        ttk.Button(buttons,text='Registrar ideia',command=lambda:self._send('IDEIA')).pack(side='left',padx=3)
        ttk.Button(buttons,text='Parar execução',command=self._stop).pack(side='left',padx=3)
        ttk.Button(buttons,text='Microfone  (Win+H)',command=self._dictate).pack(side='right',padx=3)
        ttk.Button(buttons,text='Ouvir última resposta',command=self._speak).pack(side='right',padx=3)
        self._log('system','Bem-vindo ao Kaguya Studio V3.4.\n\n1. Vincule um projeto e o vault do Obsidian.\n2. Verifique o login de Codex e Claude Code.\n3. Escreva uma tarefa e escolha o destinatário.\n\nComandos úteis: DEPOIS: para enfileirar sem interromper; IDEIA: para guardar um rascunho.\nNenhum arquivo é alterado sem autorização explícita.')

    def _build_queue(self):
        self.tasks_view=ttk.Treeview(self.tab_queue,columns=('dest','kind','state','task'),show='headings')
        for col,title,width in [('dest','Destino',120),('kind','Tipo',90),('state','Situação',120),('task','Tarefa',650)]:
            self.tasks_view.heading(col,text=title)
            self.tasks_view.column(col,width=width,stretch=col=='task')
        self.tasks_view.pack(fill='both',expand=True)
        controls=ttk.Frame(self.tab_queue);controls.pack(fill='x',pady=12)
        ttk.Button(controls,text='Atualizar fila',command=self._refresh_queue).pack(side='left')
        ttk.Button(controls,text='Executar tarefa DEPOIS selecionada',command=self._activate_task).pack(side='left',padx=7)
        ttk.Label(controls,text='Tarefas DEPOIS e IDEIA não executam sozinhas.',style='Muted.TLabel').pack(side='right')

    def _build_memory(self):
        bar=ttk.Frame(self.tab_memory);bar.pack(fill='x')
        ttk.Label(bar,text='Buscar no vault').pack(side='left',padx=4)
        self.search_var=tk.StringVar()
        ttk.Entry(bar,textvariable=self.search_var,width=40).pack(side='left',padx=8,fill='x',expand=True)
        ttk.Button(bar,text='Buscar notas',command=self._search_memory).pack(side='left',padx=4)
        ttk.Button(bar,text='Criar rascunho',command=self._stage_note).pack(side='left',padx=4)
        ttk.Button(bar,text='Revisar e sincronizar',command=self._sync_memory).pack(side='left',padx=4)
        self.memory_view=scrolledtext.ScrolledText(self.tab_memory,bg=SURFACE,fg=FG,
                               font=('Consolas',10),wrap='word',padx=12,pady=12)
        self.memory_view.pack(fill='both',expand=True,pady=10)
        self.memory_view.insert('end','Consulta notas Markdown que você já possui.\n'
           'Novos registros permanecem na pasta local de rascunhos até aprovação.\n'
           'O arquivo tasks/todo.md não é editado automaticamente pela V3.\n')
        self.memory_view.config(state='disabled')

    def _build_agents(self):
        bar=ttk.Frame(self.tab_agents);bar.pack(fill='x')
        ttk.Button(bar,text='Inventariar agentes / skills / configurações',command=self._show_inventory).pack(side='left')
        ttk.Label(bar,text='Somente leitura • não instala plugins',style='Muted.TLabel').pack(side='left',padx=15)
        self.agent_view=scrolledtext.ScrolledText(self.tab_agents,bg=SURFACE,fg=FG,
                wrap='word',font=('Consolas',10),padx=12,pady=12)
        self.agent_view.pack(expand=True,fill='both',pady=10)

    def _build_diag(self):
        bar=ttk.Frame(self.tab_diag);bar.pack(fill='x')
        ttk.Button(bar,text='Conferir autenticação das CLIs',command=self._check_clis).pack(side='left',padx=3)
        ttk.Button(bar,text='Auditoria segura (git diff)',command=lambda:self._quality(False)).pack(side='left',padx=3)
        ttk.Button(bar,text='Executar testes do projeto',command=lambda:self._quality(True)).pack(side='left',padx=3)
        ttk.Button(bar,text='Exportar auditoria Obsidian',command=self._diagnostic_report).pack(side='left',padx=3)
        self.diag_view=scrolledtext.ScrolledText(self.tab_diag,bg=SURFACE,fg=FG,
                            font=('Consolas',10),wrap='word',padx=12,pady=12)
        self.diag_view.pack(fill='both',expand=True,pady=10)
        self.diag_view.insert('end','Os testes do repositório são executados apenas quando você solicita.\n'
            'Testes podem executar código do projeto e devem ocorrer em repositórios confiáveis.\n'
            'Sucesso do comando da IA NÃO significa que o jogo compilou ou que testes passaram.\n')
        self.diag_view.config(state='disabled')

    def _log(self,speaker:str,message:str):
        if not message:return
        self.chat.config(state='normal')
        tim=datetime.now().strftime('%H:%M:%S')
        self.chat.insert('end',f'\n[{tim}] {speaker.upper()}\n',speaker)
        self.chat.insert('end',message[:7000]+'\n',('body',))
        self.chat.see('end');self.chat.config(state='disabled')
        if speaker in ('codex','claude'):
            self.last_output=message[-2200:]

    def _write_text(self,widget,content):
        widget.config(state='normal');widget.delete('1.0','end');widget.insert('end',content)
        widget.config(state='disabled')

    def _load_projects(self):
        self.projects=self.store.projects()
        self.project_names=[p['name']+f'  [{p["id"]}]' for p in self.projects]
        self.project_combo['values']=self.project_names
        if self.projects:
            idx=next((i for i,p in enumerate(self.projects) if p['id']==self.pid),0)
            self.project_combo.current(idx)
            self.pid=self.projects[idx]['id']
            self._refresh_queue();self._show_inventory()
        self._refresh_sidebar_projects();self._update_right_panel()

    def _project_selected(self,event=None):
        index=self.project_combo.current()
        if index>=0:
            self.pid=self.projects[index]['id']
            self._refresh_queue();self._show_inventory()
            self._refresh_sidebar_projects();self._update_right_panel()

    def _add_project(self):
        path=filedialog.askdirectory(title='Escolha a pasta raiz do projeto')
        if not path:return
        vault=filedialog.askdirectory(title='Escolha a pasta raiz do SEGUNDO CÉREBRO (Obsidian)')
        if not vault:return
        try:
            self.pid=self.store.add_project(Path(path).name,Path(path),Path(vault))
            self._load_projects()
            self._log('system',f'Projeto registrado: {path}\nSegundo Cérebro existente: {vault}\nNenhum arquivo original foi modificado.')
        except Exception as error:messagebox.showerror('Projeto',str(error))

    def _require_project(self):
        if self.pid is None:
            messagebox.showinfo('Projeto','Vincule primeiro um projeto e o vault do Obsidian.')
            return None
        return self.store.project(self.pid)

    def _vault(self,project):
        return Vault(Path(project['vault']),HOME/'outbox'/str(project['id']))

    def _send(self,forced=None):
        raw=self.entry.get('1.0','end').strip()
        if raw and self._submit_message(raw,forced):
            self.entry.delete('1.0','end')

    def _submit_message(self,raw:str,forced=None,target_override=None,from_quick=False):
        proj=self._require_project()
        if not proj:return False
        raw=raw.strip()
        if not raw:return False
        if forced:raw=forced+': '+raw
        default=target_override or {'Codex':'codex','Claude':'claude'}.get(self.target.get(),'equipe')
        try:kind,target,text=classify_message(raw,default)
        except ValueError as error:
            messagebox.showerror('Mensagem',str(error));return False
        # Mini-chat deliberately stays read-only even if main window has edit permission.
        write=bool(self.allow_write.get()) and not from_quick if kind=='execute' else False
        web=bool(self.allow_web.get())
        if kind=='execute' and write:
            try:changes=check_project_writable(Path(proj['directory']))
            except (ValueError,OSError) as error:
                messagebox.showerror('Edição bloqueada',str(error));return False
            warning=('Você autorizou as IAs a alterar código no repositório Git.\n'
                     'Não há API paga intencional neste aplicativo, mas o agente pode executar comandos.\n')
            if changes:warning+='\nO Git já possui alterações pendentes. Faça backup/commit primeiro.\n'+changes[:700]
            if not messagebox.askyesno('Autorizar alterações?',warning+'\nProsseguir?'):return False
        if raw.strip().lower().startswith('agora:') and self.worker and self.worker.is_alive():
            if messagebox.askyesno('Interrupção','Interromper a execução atual e deixar esta tarefa na fila?'):
                self._stop()
        tid=self.store.enqueue(self.pid,target,text,kind,write,web)
        self._log('user',f'#{tid} | @{target} | {text}')
        if kind=='idea':
            note=self._vault(proj).stage('ideia','Ideia '+str(tid),f'Projeto: {proj["name"]}\nTarefa #{tid}: {text}')
            self._log('system',f'Ideia guardada na fila e em rascunho: {note.name}. Não interrompeu os agentes.')
        elif kind=='later':
            self._log('system',f'Tarefa #{tid} guardada para depois; não será executada automaticamente.')
        else:
            self._log('system',f'Tarefa #{tid} enfileirada. Alterações: {"permitidas" if write else "bloqueadas"}.')
            self._start_worker()
        self._refresh_queue()
        return True

    def _start_worker(self):
        if self.pid is None:return
        if self.worker is not None and self.worker.is_alive():return
        self.current_cancel=threading.Event()
        project_id=self.pid
        self.worker=threading.Thread(target=self._worker_loop,args=(project_id,self.current_cancel),daemon=True)
        self.worker.start()

    def _worker_loop(self,project_id:int,cancel:threading.Event):
        proj=self.store.project(project_id)
        repo=Path(proj['directory'])
        while not cancel.is_set():
            task=self.store.claim(project_id)
            if task is None:break
            tid=task['id'];target=task['target'];write=bool(task['allow_write']);web=bool(task['allow_web'])
            self.events.put(('status',f'Executando #{tid} — {target}'))
            active_agent='codex' if target=='equipe' else target
            self.events.put(('agent_state',(active_agent,'running')))
            self.events.put(('log',('system',f'Iniciando #{tid} no projeto {proj["name"]}.')))
            logs=HOME/'logs'/str(project_id)/str(tid)
            logs.mkdir(parents=True,exist_ok=True)
            memory=self._vault(proj).search(task['title'],limit=4)
            prompt=('Você está no Kaguya Studio V3. Preserve a arquitetura do projeto e os arquivos '
                'CLAUDE.md, AGENTS.md, .claude/agents e skills existentes. NÃO instale plugins, não use '
                'APIs faturadas nem publique dados privados. Use no máximo 2 subagentes quando realmente '
                'úteis e disponíveis; prefira busca local para tarefas pequenas. '
                'Antes de implementar uma correção, tente reproduzir o problema com teste; '
                'depois verifique regressões e relate COMANDOS e RESULTADOS efetivamente observados. '
                'Pesquise referências atualizadas na web SOMENTE quando necessário e quando autorizado; '
                'traga URL, versão e data da consulta. Não altere o Obsidian diretamente. '
                'Não mova notas, não instale dependências, não faça commits nem envie dados para servidores '
                'além dos serviços oficiais já autenticados e de páginas de documentação quando autorizado. '
                'A sua resposta deve ser objetiva e separar: trabalho, evidências e pendências.\n\n'
                'TAREFA:\n'+task['title']+'\n\n'+minimal_context(memory,2900))
            try:
                if target=='equipe':
                    emit=lambda line:self.events.put(('log',('codex',line)))
                    status, output=run_cli('codex',repo,prompt,write,web,emit,logs/'codex.log',cancel)
                    if status:
                        raise RuntimeError(f'Codex retornou código {status}; verifique logs.')
                    self.events.put(('agent_state',('codex','success')))
                    active_agent='claude'
                    self.events.put(('agent_state',('claude','running')))
                    self.events.put(('status',f'Revisando #{tid} — claude'))
                    # independent review; never edits, even when writing was enabled for Codex.
                    review=('Revise independentemente o resultado da tarefa abaixo. Somente leitura; '
                            'use seus agentes já existentes apenas quando necessário. Analise Git diff e '
                            'arquivos afetados, não edite. Identifique bugs, regressões, testes ausentes; '
                            'não invente aprovações. Informe achados com evidências.\n\n'
                            'TAREFA: '+task['title']+'\n\n'
                            'RESUMO DA IMPLEMENTAÇÃO DO CODEX (não confie sem verificar):\n'+output[-4400:])
                    status, coutput=run_cli('claude',repo,review,False,web,
                        lambda line:self.events.put(('log',('claude',line))),logs/'claude_revisao.log',cancel)
                    if status:raise RuntimeError(f'Claude retornou código {status}; verifique logs.')
                    self.events.put(('agent_state',('claude','success')))
                    result='Codex executado; Claude revisou. Verifique achados e testes.\n'+coutput[-2500:]
                else:
                    status,output=run_cli(target,repo,prompt,write,web,
                        lambda line:self.events.put(('log',(target,line))),logs/f'{target}.log',cancel)
                    if status:raise RuntimeError(f'{target} retornou código {status}.')
                    self.events.put(('agent_state',(target,'success')))
                    result=output[-2500:]
                checks=run_quality(repo,False)
                summary='; '.join(q['name']+': '+q['status'] for q in checks)
                self.store.append_event(tid,'quality',summary)
                self.store.complete(tid,'executed',result+'\n'+summary)
                self.events.put(('log',('system',f'#{tid} executado. {summary}. Compilação/teste do jogo NÃO comprovados.')))
                self.events.put(('status',f'#{tid} executado — ainda requer validação'))
            except Cancelled:
                self.events.put(('agent_state',(active_agent,'cancelled')))
                self.store.complete(tid,'cancelled','Cancelado pelo usuário')
                self.events.put(('log',('warning',f'#{tid} interrompido pelo usuário.')))
                break
            except Exception as exc:
                self.events.put(('agent_state',(active_agent,'error')))
                self.store.complete(tid,'error',str(exc))
                self.events.put(('log',('warning',f'#{tid} falhou: {str(exc)}')))
                self.events.put(('status',f'Erro na tarefa #{tid}'))
                # avoid burning limits by repeatedly auto-attempting following jobs.
                break
            finally:self.events.put(('refresh',None))
        self.events.put(('worker_done',None))

    def _stop(self):
        if self.current_cancel and self.worker and self.worker.is_alive():
            self.current_cancel.set()
            self.status.set('Interrupção solicitada...')
        else:messagebox.showinfo('Execução','Não há tarefa ativa.')

    def _poll(self):
        try:
            while True:
                kind,val=self.events.get_nowait()
                if kind=='log':self._log(*val)
                elif kind=='status':
                    self.status.set(val)
                elif kind=='agent_state':
                    agent,phase=val
                    name={'codex':self.mascot,'claude':self.claude_mascot}.get(agent)
                    if name is not None:name.set_state(state_for_agent_status(agent,phase))
                    label={'running':'Trabalhando','success':'Execução concluída','error':'Erro na execução',
                           'cancelled':'Interrompido','idle':'Aguardando tarefa'}.get(phase,phase)
                    variable={'codex':self.codex_state_label,'claude':self.claude_state_label}.get(agent)
                    if variable is not None:variable.set(label)
                elif kind=='refresh':self._refresh_queue()
                elif kind=='diag':
                    self._write_text(self.diag_view,val)
                    self.tabs.select(self.tab_diag)
                elif kind=='worker_done':
                    if self.current_cancel and self.current_cancel.is_set():
                        self.status.set('Execução interrompida')
                    elif not self.status.get().startswith('Erro'):
                        self.status.set('Pronto • confira testes e logs')
                    self._refresh_queue()
        except queue.Empty:pass
        self._poll_timer=self.after(170,self._poll)

    def _refresh_queue(self):
        if not hasattr(self,'tasks_view') or self.pid is None:return
        current=self.tasks_view.selection()
        current_id=current[0] if current else None
        children=self.tasks_view.get_children()
        if children:self.tasks_view.delete(*children)
        for t in self.store.tasks(self.pid):
            state={'queued':'na fila','running':'executando','executed':'executada (não validada)',
                   'parked':'guardada','interrupted':'interrompida',
                   'cancelled':'cancelada','error':'erro'}.get(t['status'],t['status'])
            self.tasks_view.insert('', 'end', iid=str(t['id']),values=(t['target'],t['kind'],state,t['title'][:160]))
        if current_id and self.tasks_view.exists(current_id):self.tasks_view.selection_set(current_id)
        self._update_right_panel()

    def _activate_task(self):
        if self.pid is None:return
        selected=self.tasks_view.selection()
        if not selected:return
        tid=int(selected[0]);t=self.store.get_task(tid)
        if t['kind']!='later':
            messagebox.showinfo('Fila','Somente tarefas DEPOIS podem ser ativadas aqui.')
            return
        write=self.allow_write.get()
        if write:
            try:changes=check_project_writable(Path(self.store.project(self.pid)['directory']))
            except ValueError as error:
                messagebox.showerror('Git',str(error));return
            if not messagebox.askyesno('Autorizar alterações?',
                'Esta tarefa poderá editar arquivos do projeto.\n'
                + ('Há alterações pendentes no Git.\n' if changes else '')+'Prosseguir?'):return
        self.store.activate_later(tid,write,self.allow_web.get())
        self._refresh_queue();self._start_worker()

    def _search_memory(self):
        proj=self._require_project()
        if not proj:return
        topic=self.search_var.get().strip()
        if not topic:return
        hits=self._vault(proj).search(topic,limit=10)
        self._write_text(self.memory_view,'\n\n'.join(
            f'{n+1}. {h["path"]} (pontuação {h["score"]})\n{h["excerpt"]}' for n,h in enumerate(hits))
            if hits else 'Nenhuma nota encontrada. Verifique o termo e a pasta do vault.')

    def _stage_note(self):
        proj=self._require_project()
        if not proj:return
        title=simpledialog.askstring('Novo rascunho','Título da nota:')
        if not title:return
        content=simpledialog.askstring('Conteúdo','Resumo da descoberta, ideia ou referência:')
        if not content:return
        name=self._vault(proj).stage('aprendizado',title,content)
        messagebox.showinfo('Rascunho',f'Criado localmente: {name.name}\nO Obsidian ainda não foi modificado.')

    def _sync_memory(self):
        proj=self._require_project()
        if not proj:return
        vault=self._vault(proj)
        preview=vault.sync_preview()
        if not preview:
            messagebox.showinfo('Sincronizar','Não há novos rascunhos.');return
        names=[p['filename'] for p in preview if not p['exists']]
        explanation='\n'.join(p['destination'] for p in preview[:15])
        if not messagebox.askyesno('Sincronização create-only',
                f'As seguintes notas NOVAS serão criadas:\n{explanation}\n\n'
                'Nenhum arquivo existente será sobrescrito. Confirmar?'):return
        done=vault.sync_approved(names)
        messagebox.showinfo('Sincronização',f'{len(done)} nota(s) criadas no vault. Abra o Obsidian para revisar.')

    def _show_inventory(self):
        proj=self._require_project() if self.pid is None and hasattr(self,'agent_view') else (self.store.project(self.pid) if self.pid is not None else None)
        if not proj:return
        details=inventory(Path(proj['directory']),CATALOG)
        intro=('CATÁLOGO DO USUÁRIO: '+str(details['catalog_count'])+' agentes listados.\n'
             'Este arquivo é um inventário histórico; não comprova instalações reais.\n\n')
        rest='\n\n'.join(f'{key}:\n'+( '\n'.join('  • '+x for x in value) if isinstance(value,list) else str(value))
                        for key,value in details.items() if key not in ('catalog_count',))
        self._write_text(self.agent_view,intro+rest+'\n\nNenhum agente, skill ou plugin foi instalado ou modificado.\n')

    def _check_clis(self):
        proj=self._require_project()
        if not proj:return
        def job():
            lines=[]
            for cli in ('codex','claude'):
                try:lines.append(check_subscription(cli,Path(proj['directory'])))
                except Exception as ex:lines.append(f'{cli}: NÃO VERIFICADO — {ex}')
            self.events.put(('diag','\n\n'.join(lines)+'\n\n'
                'IMPORTANTE: a verificação de login não garante ausência de cobranças por configurações externas.\n'
                'Confira a conta e as configurações dos clientes oficiais.'))
        threading.Thread(target=job,daemon=True).start()

    def _quality(self,tests:bool):
        proj=self._require_project()
        if not proj:return
        if tests and not messagebox.askyesno('Executar código do repositório?',
           'Compilações e testes podem executar scripts do próprio projeto e modificar arquivos de build.\n'
           'Use apenas projetos confiáveis. Deseja executar?'):return
        def job():
            report=run_quality(Path(proj['directory']),tests)
            out='\n\n'.join(f'{r["name"]}: {r["status"]}\n{r["details"]}' for r in report)
            self.events.put(('diag',out))
        threading.Thread(target=job,daemon=True).start()

    def _diagnostic_report(self):
        proj=self._require_project()
        if not proj:return
        def job():
            try:
                dest=HOME/'diagnosticos'/f'projeto_{proj["id"]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                path=export_report(Path(proj['directory']),Path(proj['vault']),CATALOG,dest)
                self.events.put(('diag',f'Auditoria (somente leitura) gravada em:\n{path}\n\n'
                                 'O relatório mostra contagens, links possivelmente quebrados, duplicatas '
                                 'e inventário de agentes/skills. Não contém corpo de notas.\n'
                                 'Revise caminhos e nomes antes de compartilhá-lo.'))
            except Exception as exc:self.events.put(('diag','Falha na auditoria: '+str(exc)))
        threading.Thread(target=job,daemon=True).start()

    def _dictate(self):
        self.entry.focus_set()
        messagebox.showinfo('Ditado do Windows','Aperte Windows + H para ditar no campo da mensagem.\n'
            'Esta versão não contém um modo Live full-duplex. O ditado utiliza o recurso do próprio Windows.')

    def _speak(self):
        if not self.last_output:
            messagebox.showinfo('Voz','Ainda não há resposta para ler.');return
        if os.name!='nt':
            messagebox.showinfo('Voz','Leitura por voz local foi preparada para Windows.');return
        script=('Add-Type -AssemblyName System.Speech; '
                '$v=New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                '$v.Speak([Console]::In.ReadToEnd())')
        def job():
            try:
                subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',script],
                    input=self.last_output[:1000],capture_output=True,text=True,timeout=70)
            except (OSError,subprocess.TimeoutExpired):pass
        threading.Thread(target=job,daemon=True).start()

    def destroy(self):
        if hasattr(self,'_poll_timer'):
            try:self.after_cancel(self._poll_timer)
            except tk.TclError:pass
        for mascot in getattr(self,'mascots',[]):mascot.close()
        super().destroy()

    def _close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno('Encerrar','Há um agente trabalhando. Encerrar interromperá a tarefa. Continuar?'):
                return
            if self.current_cancel:self.current_cancel.set()
        self.destroy()


if __name__ == '__main__':
    try:
        app=Studio()
        if '--mascote' in sys.argv:
            app.only_mascot=True
            for mascot in app.mascots:mascot.show()
            app.float_label.set('Ocultar Kaguya')
            app.withdraw()
        app.mainloop()
    except tk.TclError as exc:
        print('Falha na interface grafica Tkinter:',exc,file=sys.stderr)
        raise
