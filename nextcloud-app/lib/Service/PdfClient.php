<?php
declare(strict_types=1);

namespace OCA\StrumentiPdf\Service;

use OCA\StrumentiPdf\AppInfo\Application;
use OCP\Files\File;
use OCP\Http\Client\IClientService;
use OCP\ICache;
use OCP\ICacheFactory;
use OCP\IConfig;
use Psr\Log\LoggerInterface;

/** Parla con il server Plico (pdf_url, api_key nelle impostazioni dell'app). */
class PdfClient {
	private ICache $cache;

	public function __construct(
		private IClientService $clients,
		private IConfig $config,
		ICacheFactory $cacheFactory,
		private LoggerInterface $logger,
	) {
		$this->cache = $cacheFactory->createDistributed('strumentipdf');
	}

	private function url(): string {
		return rtrim($this->config->getAppValue(Application::APP_ID, 'pdf_url', ''), '/');
	}

	public function configured(): bool {
		return $this->url() !== '';
	}

	private function headers(): array {
		$h = ['Accept-Language' => 'it'];
		$key = $this->config->getAppValue(Application::APP_ID, 'api_key', '');
		if ($key !== '') {
			$h['apikey'] = $key;
		}
		return $h;
	}

	/** Funzioni attive sul server e catene salvate (in cache per 5 minuti). */
	public function config(): array {
		$cached = $this->cache->get('config');
		if (is_array($cached)) {
			return $cached;
		}
		$out = ['features' => [], 'chains' => []];
		try {
			$c = $this->clients->newClient();
			$out['features'] = json_decode((string)$c->get($this->url() . '/api/features', ['timeout' => 5, 'headers' => $this->headers()])->getBody(), true) ?: [];
			$chains = json_decode((string)$c->get($this->url() . '/api/chains', ['timeout' => 5, 'headers' => $this->headers()])->getBody(), true);
			$out['chains'] = array_map(fn ($x) => ['id' => $x['id'], 'name' => $x['name']], $chains['chains'] ?? []);
		} catch (\Throwable $e) {
			$this->logger->warning('Strumenti PDF: server non raggiungibile: ' . $e->getMessage(), ['app' => Application::APP_ID]);
		}
		$this->cache->set('config', $out, 300);
		return $out;
	}

	/**
	 * Manda i file a un endpoint e restituisce [contenuto, nome proposto dal server].
	 * @param File[] $files
	 */
	public function run(string $endpoint, array $files, string $field, array $fields): array {
		$multipart = [];
		foreach ($fields as $name => $value) {
			$multipart[] = ['name' => $name, 'contents' => is_bool($value) ? ($value ? 'true' : 'false') : (string)$value];
		}
		foreach ($files as $f) {
			$multipart[] = ['name' => $field, 'contents' => $f->fopen('r'), 'filename' => $f->getName()];
		}
		try {
			$resp = $this->clients->newClient()->post($this->url() . '/api/' . $endpoint, [
				'multipart' => $multipart,
				'headers' => $this->headers(),
				'timeout' => 1800,
				'http_errors' => false,
			]);
		} catch (\Throwable $e) {
			throw new PdfException('Il server Plico non risponde');
		}
		$body = (string)$resp->getBody();
		if ($resp->getStatusCode() !== 200) {
			$detail = json_decode($body, true)['detail'] ?? ('HTTP ' . $resp->getStatusCode());
			throw new PdfException(is_string($detail) ? $detail : 'errore');
		}
		$name = '';
		if (preg_match('/filename\*=UTF-8\'\'([^;]+)/i', $resp->getHeader('Content-Disposition'), $m)) {
			$name = rawurldecode($m[1]);
		} elseif (preg_match('/filename="?([^";]+)"?/i', $resp->getHeader('Content-Disposition'), $m)) {
			$name = $m[1];
		}
		return [$body, $name];
	}
}
