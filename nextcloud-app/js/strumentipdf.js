/* Strumenti PDF: tasto destro su uno o piu' PDF -> "Strumenti PDF" -> operazione.
 * Niente build: usa il registro di @nextcloud/files v4 (window._nc_files_scope.v4_0), come registerFileAction(). */
(function () {
	'use strict'
	const stateEl = document.getElementById('initial-state-strumentipdf-config')
	if (!stateEl) return
	let C
	try { C = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(stateEl.value), c => c.charCodeAt(0)))) } catch (e) { return }
	const F = C.features || {}

	const scope = (window._nc_files_scope ??= {})
	const g = (scope.v4_0 ??= {})
	g.fileActions ??= new Map()
	function register(action) {
		if (g.fileActions.has(action.id)) return
		g.fileActions.set(action.id, action)
		if (g.registry && typeof g.registry.dispatchEvent === 'function') {
			g.registry.dispatchEvent(new CustomEvent('register:action', { detail: action }))
		}
	}

	// ---- avvisi
	let toastBox
	function toast(text, kind = 'info', ms = 6000) {
		if (!toastBox) {
			toastBox = document.createElement('div')
			toastBox.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:100000;display:flex;flex-direction:column;gap:8px;max-width:min(420px,calc(100vw - 32px))'
			document.body.appendChild(toastBox)
		}
		const colors = { info: 'var(--color-primary-element,#0082c9)', success: 'var(--color-success,#2d7b41)', error: 'var(--color-error,#db0606)' }
		const t = document.createElement('div')
		t.setAttribute('role', kind === 'error' ? 'alert' : 'status')
		t.className = 'strumentipdf-toast'
		t.style.cssText = `background:var(--color-main-background,#fff);color:var(--color-main-text,#222);border-left:4px solid ${colors[kind]};border-radius:var(--border-radius-large,10px);box-shadow:0 2px 12px rgba(0,0,0,.25);padding:10px 14px;font-size:14px;line-height:1.4;cursor:pointer;word-break:break-word`
		t.textContent = text
		t.onclick = () => t.remove()
		toastBox.appendChild(t)
		if (ms) setTimeout(() => t.remove(), ms)
		return t
	}

	// ---- richiesta della password, in una finestra della pagina (niente prompt del browser)
	function askPassword(title) {
		return new Promise(resolve => {
			const bg = document.createElement('div')
			bg.style.cssText = 'position:fixed;inset:0;z-index:100001;background:rgba(0,0,0,.4);display:grid;place-items:center'
			bg.innerHTML = `<form style="background:var(--color-main-background,#fff);color:var(--color-main-text,#222);border-radius:12px;padding:20px;min-width:min(360px,90vw);display:grid;gap:12px;box-shadow:0 8px 30px rgba(0,0,0,.3)">
				<b></b><input type="password" autocomplete="new-password" required style="width:100%">
				<div style="display:flex;gap:8px;justify-content:flex-end"><button type="button">Annulla</button><button type="submit" class="primary">OK</button></div></form>`
			bg.querySelector('b').textContent = title
			const done = v => { bg.remove(); resolve(v) }
			bg.querySelector('button[type=button]').onclick = () => done(null)
			bg.querySelector('form').onsubmit = e => { e.preventDefault(); done(bg.querySelector('input').value) }
			bg.onclick = e => { if (e.target === bg) done(null) }
			document.body.appendChild(bg)
			bg.querySelector('input').focus()
		})
	}

	const url = p => (window.OC && OC.generateUrl ? OC.generateUrl(p) : '/index.php' + p)
	const token = () => (window.OC && OC.requestToken) || document.head.dataset.requesttoken || ''

	function showNewFile(src, ctx, r) {
		try {
			if (!ctx.folder || r.parentId !== ctx.folder.fileid || !window._nc_event_bus) return
			const node = new src.constructor({
				id: r.fileId, source: ctx.folder.source.replace(/\/$/, '') + '/' + encodeURIComponent(r.name),
				root: src.root, owner: src.owner, mime: r.mime, size: r.size, mtime: new Date(r.mtime * 1000),
				permissions: ctx.folder.permissions, attributes: {},
			})
			window._nc_event_bus.emit('files:node:created', node)
		} catch (e) {
			console.debug('strumentipdf: aggiorna la cartella per vedere il file', e)
		}
	}

	async function run(nodes, tool, label, ctx, extra = {}) {
		if (tool === 'protect' || tool === 'unlock') {
			const pw = await askPassword(tool === 'protect' ? 'Password per aprire il PDF' : 'Password attuale del PDF')
			if (pw === null) return
			extra.password = pw
		}
		const what = nodes.length > 1 ? `${nodes.length} file` : `«${nodes[0].basename}»`
		const wait = toast(`${label}: ${what}…`, 'info', 0)
		try {
			const r = await fetch(url('/apps/strumentipdf/run'), {
				method: 'POST', credentials: 'same-origin',
				headers: { 'Content-Type': 'application/json', requesttoken: token(), 'OCS-APIRequest': 'true' },
				body: JSON.stringify({ fileIds: nodes.map(n => n.fileid), tool, ...extra }),
			})
			let d = {}
			try { d = await r.json() } catch (e) { /* risposta vuota */ }
			if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`)
			wait.remove()
			toast(d.created.length === 1 ? `Creato «${d.created[0].name}»` : `Creati ${d.created.length} file`, 'success')
			d.created.forEach(c => showNewFile(nodes[0], ctx, c))
		} catch (e) {
			wait.remove()
			toast(`${label} non riuscito: ${e.message}`, 'error', 15000)
		}
	}

	const isPdf = n => n && n.type === 'file' && (n.permissions & 1) && (n.mime === 'application/pdf' || /\.pdf$/i.test(n.basename || ''))
	const allPdf = ctx => !!ctx.nodes && ctx.nodes.length > 0 && ctx.nodes.every(isPdf)
	const ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11zM8 12h8v2H8zm0 4h5v2H8z"/></svg>'

	register({
		id: 'strumentipdf', displayName: () => 'Strumenti PDF', iconSvgInline: () => ICON, order: 31,
		enabled: allPdf, exec: async () => null, execBatch: async ctx => ctx.nodes.map(() => null),
	})

	const TOOLS = [
		['merge', 'Unisci in un PDF', ctx => ctx.nodes.length >= 2],
		['compress', 'Comprimi'],
		['compress-high', 'Comprimi molto'],
		['ocr', 'Rendi ricercabile (OCR)', () => !!F.ocr],
		['numbers', 'Numera le pagine'],
		['rotate', 'Ruota di 90°'],
		['protect', 'Proteggi con password'],
		['unlock', 'Togli la password'],
		['clean', 'Togli i dati nascosti'],
		['pdfa', 'Converti in PDF/A', () => !!F.ocr],
		['repair', 'Ripara'],
	]
	TOOLS.forEach(([tool, label, cond], i) => register({
		id: 'strumentipdf-' + tool, parent: 'strumentipdf', displayName: () => label, iconSvgInline: () => ICON, order: i,
		enabled: ctx => allPdf(ctx) && (!cond || cond(ctx)),
		exec: async ctx => { run(ctx.nodes, tool, label, ctx); return null },
		execBatch: async ctx => { run(ctx.nodes, tool, label, ctx); return ctx.nodes.map(() => null) },
	}))
	;(C.chains || []).forEach((c, i) => register({
		id: 'strumentipdf-chain-' + c.id, parent: 'strumentipdf', displayName: () => `Catena: ${c.name}`, iconSvgInline: () => ICON,
		order: 100 + i, enabled: allPdf,
		exec: async ctx => { run(ctx.nodes, 'chain', c.name, ctx, { chain: c.id }); return null },
		execBatch: async ctx => { run(ctx.nodes, 'chain', c.name, ctx, { chain: c.id }); return ctx.nodes.map(() => null) },
	}))
})()
