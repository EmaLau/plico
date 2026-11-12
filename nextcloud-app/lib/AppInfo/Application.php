<?php
declare(strict_types=1);

namespace OCA\StrumentiPdf\AppInfo;

use OCA\Files\Event\LoadAdditionalScriptsEvent;
use OCA\StrumentiPdf\Listener\LoadScriptsListener;
use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;

class Application extends App implements IBootstrap {
	public const APP_ID = 'strumentipdf';

	public function __construct() {
		parent::__construct(self::APP_ID);
	}

	public function register(IRegistrationContext $context): void {
		$context->registerEventListener(LoadAdditionalScriptsEvent::class, LoadScriptsListener::class);
	}

	public function boot(IBootContext $context): void {
	}
}
