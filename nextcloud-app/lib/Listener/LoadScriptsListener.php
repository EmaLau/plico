<?php
declare(strict_types=1);

namespace OCA\StrumentiPdf\Listener;

use OCA\Files\Event\LoadAdditionalScriptsEvent;
use OCA\StrumentiPdf\AppInfo\Application;
use OCA\StrumentiPdf\Service\PdfClient;
use OCP\AppFramework\Services\IInitialState;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\Util;

/** @template-implements IEventListener<LoadAdditionalScriptsEvent> */
class LoadScriptsListener implements IEventListener {
	public function __construct(
		private PdfClient $client,
		private IInitialState $initialState,
	) {
	}

	public function handle(Event $event): void {
		if (!$event instanceof LoadAdditionalScriptsEvent || !$this->client->configured()) {
			return;
		}
		// funzioni attive e catene salvate arrivano con la pagina: il JS registra il menu subito
		$this->initialState->provideLazyInitialState('config', fn () => $this->client->config());
		Util::addScript(Application::APP_ID, 'strumentipdf');
	}
}
