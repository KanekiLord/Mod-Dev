"""Read-only diagnostic of installed agent files, Obsidian links and local setup.

Does not copy note bodies or read/write credentials. Exports only metadata.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from core import inventory, Vault, now


WIKI=re.compile(r'(?<!!)\[\[([^\]]+)\]\]')


def vault_audit(root:Path)->dict:
    root=Path(root).resolve()
    names=set()
    notes=[]
    hashes=defaultdict(list)
    groups=Counter()
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[x for x in dirs if x not in Vault.SKIP_DIRS and not (Path(base)/x).is_symlink()]
        for file in files:
            path=Path(base)/file
            if path.is_symlink() or not file.endswith('.md'):continue
            try:
                if path.stat().st_size>750000:continue
                rel=path.relative_to(root).as_posix()
                body=path.read_text(encoding='utf-8-sig',errors='replace')
            except (OSError,UnicodeError):continue
            names.add(path.stem.lower())
            names.add(rel.lower().removesuffix('.md'))
            groups[rel.split('/')[0]]+=1
            notes.append((rel,body))
            hashes[sha256(body.encode('utf-8')).hexdigest()].append(rel)
            if len(notes)>=4000:break
        if len(notes)>=4000:break
    broken=[]; linked=Counter()
    for path,content in notes:
        for raw in WIKI.findall(content):
            value=raw.split('|',1)[0].split('#',1)[0].strip().replace('\\','/')
            if not value:continue
            name=Path(value).stem.lower()
            if Path(value).suffix.lower() in ('.png','.jpg','.jpeg','.gif','.webp','.pdf','.canvas','.mp4'):
                continue
            if name in names or value.lower().removesuffix('.md') in names:
                linked[name]+=1
            else:
                broken.append(value)
    duplicates=[v for v in hashes.values() if len(v)>1]
    return {
        'markdown_notes':len(notes),
        'notes_by_root_folder':dict(groups.most_common()),
        'wiki_links_unresolved':len(broken),
        'unresolved_examples':list(dict.fromkeys(broken))[:20],
        'duplicate_content_groups':len(duplicates),
        'duplicate_examples':[x[:4] for x in duplicates[:10]],
        'note':'Links sem destino podem usar aliases/Canvas; conferência manual necessária. Não equivale a validação completa.'
    }


def build_report(project:Path,vault:Path,catalog:Path)->dict:
    project=Path(project).resolve();vault=Path(vault).resolve()
    result={
        'generated_at':now(),
        'project':{
            'path':str(project),
            'has_claude_md':(project/'CLAUDE.md').is_file(),
            'has_agents_md':(project/'AGENTS.md').is_file(),
            'claude_settings_exists':(project/'.claude'/'settings.json').is_file(),
            'codex_config_exists':(project/'.codex'/'config.toml').is_file(),
        },
        'cli_on_path':{'codex':bool(shutil.which('codex')),
                       'claude':bool(shutil.which('claude')),
                       'git':bool(shutil.which('git'))},
        'agent_inventory':inventory(project,catalog),
        'vault':vault_audit(vault),
        'notice':'O relatório não contém conteúdo das notas, tokens, senhas ou arquivos de configuração. Revise nomes e caminhos antes de compartilhar.'
    }
    return result


def export_report(project:Path,vault:Path,catalog:Path,output:Path)->Path:
    report=build_report(project,vault,catalog)
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return output
