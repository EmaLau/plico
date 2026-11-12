<?php
declare(strict_types=1);

namespace OCA\StrumentiPdf\Controller;

use OCA\StrumentiPdf\Service\PdfClient;
use OCA\StrumentiPdf\Service\PdfException;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\Attribute\FrontpageRoute;
use OCP\AppFramework\Http\Attribute\NoAdminRequired;
use OCP\AppFramework\Http\JSONResponse;
use OCP\Files\File;
use OCP\Files\Folder;
use OCP\Files\IRootFolder;
use OCP\IRequest;
use OCP\IUserSession;

class PdfController extends Controller {
	/** strumento -> [endpoint, campo dei file, suffisso del nome, opzioni fisse] */
	private const TOOLS = [
		'compress' => ['compress', 'file', 'compresso', ['level' => 'medium']],
		'compress-high' => ['compress', 'file', 'compresso', ['level' => 'high']],
		'merge' => ['merge', 'files', 'unito', []],
		'ocr' => ['ocr', 'file', 'ocr', ['lang' => 'ita+eng']],
		'pdfa' => ['pdfa', 'file', 'pdfa', []],
		'numbers' => ['stamp', 'file', 'numerato', ['numbers' => true, 'num_fmt' => '{n} / {tot}']],
		'rotate' => ['rotate', 'file', 'ruotato', ['angle' => 90]],
		'clean' => ['metadata', 'file', 'pulito', ['clean' => true]],
		'repair' => ['repair', 'file', 'riparato', []],
		'protect' => ['protect', 'file', 'protetto', []],
		'unlock' => ['unlock', 'file', 'sbloccato', []],
		'chain' => ['chain', 'files', 'elaborato', []],
	];

	public function __construct(
		IRequest $request,
		private PdfClient $client,
		private IRootFolder $rootFolder,
		private IUserSession $userSession,
	) {
		parent::__construct('strumentipdf', $request);
	}

	#[NoAdminRequired]
	#[FrontpageRoute(verb: 'POST', url: '/run')]
	public function run(array $fileIds, string $tool, string $password = '', string $chain = ''): JSONResponse {
		try {
			if (!isset(self::TOOLS[$tool])) {
				throw new PdfException('Strumento sconosciuto');
			}
			[$endpoint, $field, $suffix, $fields] = self::TOOLS[$tool];
			$uid = $this->userSession->getUser()?->getUID() ?? throw new PdfException('Non autenticato');
			$userFolder = $this->rootFolder->getUserFolder($uid);
			$files = [];
			foreach (array_slice($fileIds, 0, 100) as $id) {
				$node = $userFolder->getFirstNodeById((int)$id);
				if (!$node instanceof File || !$node->isReadable()) {
					throw new PdfException('File non trovato');
				}
				$files[] = $node;
			}
			if (!$files) {
				throw new PdfException('Nessun file');
			}
			if ($tool === 'merge' && count($files) < 2) {
				throw new PdfException('Scegli almeno due file da unire');
			}
			if (in_array($tool, ['protect', 'unlock'], true)) {
				$fields['password'] = $password;
			}
			if ($tool === 'chain') {
				$fields['chain'] = $chain;
			}
			$parent = $files[0]->getParent();
			if (!$parent->isCreatable()) {
				throw new PdfException('Non puoi creare file in questa cartella');
			}
			// "merge" e "chain" mandano tutti i file insieme; gli altri strumenti un file alla volta
			$batches = in_array($tool, ['merge', 'chain'], true) && !($tool === 'chain' && count($files) > 1) ? [$files] : array_map(fn ($f) => [$f], $files);
			$created = [];
			foreach ($batches as $batch) {
				[$data, $serverName] = $this->client->run($endpoint, $batch, $field, $fields);
				$ext = strtolower(pathinfo($serverName, PATHINFO_EXTENSION)) ?: 'pdf';
				$base = pathinfo($batch[0]->getName(), PATHINFO_FILENAME);
				$name = $this->freeName($batch[0]->getParent(), "$base-$suffix.$ext");
				$new = $batch[0]->getParent()->newFile($name, $data);
				$created[] = ['fileId' => $new->getId(), 'name' => $new->getName(), 'parentId' => $new->getParent()->getId(),
					'mime' => $new->getMimetype(), 'size' => $new->getSize(), 'mtime' => $new->getMTime()];
			}
			return new JSONResponse(['created' => $created]);
		} catch (PdfException $e) {
			return new JSONResponse(['error' => $e->getMessage()], Http::STATUS_BAD_REQUEST);
		}
	}

	private function freeName(Folder $folder, string $name): string {
		if (!$folder->nodeExists($name)) {
			return $name;
		}
		$base = pathinfo($name, PATHINFO_FILENAME);
		$ext = pathinfo($name, PATHINFO_EXTENSION);
		for ($i = 2; ; $i++) {
			$try = "$base ($i)." . $ext;
			if (!$folder->nodeExists($try)) {
				return $try;
			}
		}
	}
}
