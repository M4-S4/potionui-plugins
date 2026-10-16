# Video Producer : guide utilisateur

English: [Video Producer: user guide](/docs?doc=plugin/video-producer/user-guide) (file `docs/user-guide.md`).

Ce guide explique comment réaliser un court film avec Video Producer. Les libellés de l’interface sont écrits en **gras**. Un chapitre qui décrit quelque chose qui n’existe pas encore se termine par « Disponible à partir de l’étape N ». Le guide d’administration est une page distincte que seuls les admins voient.

## 1. Ce qu’est Video Producer

Video Producer est un plugin PotionUI de montage audiovisuel, de génération de séquences par IA, de direction artistique, de création sonore et de préparation de scènes 3D, dans un même espace. Vous écrivez un synopsis, vous le découpez en plans, vous générez des prises brouillon rapides, vous choisissez la meilleure, vous la passez en final, puis vous montez, raccordez les couleurs, mixez et livrez. Il s’ouvre depuis l’entrée **Video Producer** de la barre latérale.

Avant de commencer :

- Un admin doit avoir préparé au moins un moteur (ce poste, un serveur d’atelier ou un modèle cloud) et au moins un preset vidéo qui vous est attribué. Si la barre Production n’affiche aucun moteur, voyez le chapitre 16.
- Votre admin règle aussi la résolution des brouillons et peut limiter les minutes GPU que vous pouvez utiliser par mois.
- Le modèle MiniMax-H3 est sous une licence qui exclut son usage, et tout ce qu’il génère, dans l’Union européenne, au Royaume-Uni, aux États-Unis et en Corée du Sud sans autorisation individuelle de MiniMax, et qui demande qu’un produit commercial affiche « MiniMax H3 » de façon visible. Demandez à votre admin avant de l’utiliser.

L’interface est en anglais par défaut et existe aussi en français (chapitre 13).

## 2. Le parcours en huit étapes

1. **Créer un projet.** **Fichier › Nouveau projet…** (ou **Fichier › Ouvrir…** pour un projet existant). Dans **Propriétés du projet…** vous réglez le nom, le format (16:9, 2.39:1, 9:16, 1:1 ou 4:5), la résolution (720p, 1080p ou 4K) et la cadence (24, 25 ou 30 i/s). Résultat : un projet vide, enregistré au fil de votre travail.
2. **Définir la direction globale.** Dans l’espace **Director IA**, onglet **Direction** : univers et intention, personnages et identité, direction photographique, palette et éclairage, rythme et continuité. Résultat : un texte qui guide toutes les générations.
3. **Ajouter les références.** Dans **Director IA**, onglet **Références** : identités, décors 3D et guides de mouvement. Résultat : ce qui doit rester identique d’un plan à l’autre.
4. **Découper le film en plans.** Dans l’espace **Storyboard** : écrivez le synopsis, cliquez sur **Proposer un découpage**, gardez les plans voulus et ajustez leurs instructions locales. Résultat : une rangée de cartes de plans.
5. **Générer des brouillons.** Dans la barre Production, qualité **Brouillon**, puis **Générer la sélection** (⌘ G). L’estimation indique le temps GPU et le quota. Résultat : des prises brouillon A, B, etc.
6. **Choisir une prise et la passer en final.** Dans l’inspecteur, onglet **Prises** : comparez, cliquez sur **Utiliser**, puis sur **Final** pour la meilleure prise. Résultat : le plan passe de Brouillon à Final.
7. **Monter, raccorder et mixer.** Fondus sur les clips, raccord de couleur dans l’onglet **Couleur** de l’inspecteur, console dans **Mixage**. Résultat : une séquence terminée.
8. **Livrer.** **Fichier › Exporter la vidéo…**, **Exporter vers un autre logiciel…** ou **Exporter les sous-titres…**. Résultat : des fichiers à télécharger.

Disponible à partir de l’étape 2 : l’interface des huit étapes. À partir de l’étape 3 : les projets enregistrés. À partir de l’étape 4 : les brouillons et les finals. À partir de l’étape 6 : la livraison.

## 3. L’écran

La page compte cinq niveaux, du plus large au plus local :

- **Barre de menus.** Dix menus, dans cet ordre : **Video Producer**, **Fichier**, **Édition**, **Montage**, **Plan**, **Production**, **Audio**, **Présentation**, **Fenêtre**, **Aide**. Le menu **Video Producer** contient À propos, **Préférences…**, **Raccourcis clavier** et **Rechercher une commande…**.
- **Barre projet.** Le nom du projet et son état d’enregistrement, le sélecteur d’espaces (**Médias**, **Director IA**, **Storyboard**, **Scène 3D**, **Mixage**), **Importer**, **Exporter**, **Assistant** et les boutons qui affichent ou masquent le panneau latéral et l’inspecteur.
- **Barre Production.** Elle cible ce qu’il faut générer et porte le seul bouton principal de la page, **Générer la sélection** (chapitre 6).
- **En-têtes de zone et barre d’outils de la timeline.** Un titre et des compteurs à gauche, de petites icônes à droite.
- **Contenu.** De petits boutons qui apparaissent au survol ou à la sélection.

Une règle à retenir : toutes les autres entrées (Storyboard, panneau latéral, Director IA) ne font que cibler ce qu’il faut générer ; c’est la barre Production qui agit. Un menu n’affiche « … » que si la commande ouvre une fenêtre qui demande une saisie. La barre d’état, en bas, indique le nombre de plans et la durée, l’outil actif, la sélection, la plage, le nombre de points de direction à vérifier, la file de génération, le magnétisme, votre **Quota GPU** et un rappel de la langue (`EN` ou `FR`).

Disponible à partir de l’étape 2.

## 4. Les espaces de travail

Chaque espace change le panneau de gauche et le centre. L’inspecteur, à droite, suit votre sélection dans tous.

### Médias

La bibliothèque du projet et la **galerie PotionUI** dans un seul panneau. Filtrez avec les pastilles de collections (**Toutes**, **Galerie PotionUI**, **Générés** et les vôtres), cherchez par nom sans vous soucier des accents, double-cliquez pour prévisualiser, glissez vers la timeline. Pour un élément sélectionné : **Prévisualiser**, **Au montage** et, pour les images et les vidéos, **Utiliser comme frame à la tête de lecture**.

### Director IA

Trois onglets :

- **Direction.** Montre ce qui guide la génération : la direction globale, les instructions locales de la plage, les références et les contrôles. En dessous : **Points à vérifier**, le **Profil H3 du projet** (FL2VA, Ref2VA ou Hybrid AV, chapitre 9) et la **Direction globale** elle-même, en cinq champs, avec un compteur qui s’arrête à 4000 caractères.
- **Références.** Trois familles : **Images et identité**, **Décors 3D** et **Guides de mouvement**. Une référence est globale (elle accompagne toutes les générations) ou ne s’applique qu’à une plage ; **Associer à la plage** règle le second cas. **Référence** en ajoute une.
- **Résultats.** Les prises de chaque plan, **Comparer**, **À reprendre**, **Utiliser**, la file de génération et **Assembler les prises choisies**.

### Storyboard

À gauche : le **Synopsis** (une phrase devient un plan), **Proposer un découpage** et le **Découpage proposé**, où vous cochez les plans à garder avant de cliquer sur **Ajouter N plans à la fin**, puis **À produire**, avec le temps restant pour les brouillons et pour les finals, et **Continuité**. Au centre : une carte par plan, dans l’ordre, avec son étape (**Source**, **À générer**, **Brouillon** ou **Final**), son nombre de prises et son instruction locale. Glissez une carte pour la déplacer. Le bouton d’une carte suit son étape : **Générer**, **Passer en final**, **Voir les prises** ou **Régénérer**.

### Scène 3D

Les **Scènes**, les **Plans 3D sur la timeline**, les **Trajectoires prédéfinies** (Orbite, Travelling avant, Élévation), la caméra et ses positions clés dans l’inspecteur, et les **Sorties pour la génération** : **Capturer une frame** et **Générer la vidéo de contrôle**. Cet espace est en partie simulé : voyez le chapitre 15.

### Mixage

Les **Sons du projet**, l’**Atelier Sound design**, les **Rôles** (Dialogue, Musique, Ambiance, SFX) et la console de mixage : faders, **M** et **S**, panoramique, égaliseur, compresseur, filtre, envois de réverbération et de délai, vumètres et un mode d’automation. La console joue vos vrais fichiers audio. L’atelier et les courbes d’automation sont simulés : voyez le chapitre 15.

Disponible à partir de l’étape 2. Vos propres médias et les projets enregistrés : à partir de l’étape 3.

## 5. Inspecteur

L’inspecteur suit la sélection. Pour un plan, il a trois onglets :

- **Plan.** Le nom, l’étape, la durée et la source, les fondus, et la marque **Favori** ou **Rejeté**.
- **Prises.** Les prises du plan (chapitre 7).
- **Couleur.** Le scope de luminance, le raccord avec le plan précédent, les préréglages et les réglages fins (chapitre 10).

Les autres éléments ont leur propre panneau : clip audio, titre, prompt de plan, frame de référence, Control video, plan 3D, marqueur, référence et tranche de console. Dans l’espace **Scène 3D**, avec un plan 3D sélectionné, l’inspecteur affiche la **Caméra**. Sans sélection, il montre le projet et un bouton **Propriétés du projet…**.

Disponible à partir de l’étape 2.

## 6. Barre Production et estimation

La barre Production se lit comme une phrase : une cible (**Plan**, **Plage** ou **Séquence**), la plage et ce qu’elle contient, une qualité (**Brouillon** ou **Final**), un mode de sortie, un moteur, l’**Atelier avancé**, puis l’estimation, la file et **Générer la sélection**.

- Le mode de sortie **Génération IA** est le mode réel. **Rendu 3D** et **Rendu 3D + IA** sont simulés (chapitre 15).
- Le menu du moteur liste ce que votre admin a activé : **Ce poste**, **Serveur atelier** et des modèles cloud.
- L’**Atelier avancé** a trois étapes : **Sources et guides**, **Moteur et Hybrid builder** et **Son et livraison**.

L’estimation donne le temps GPU, la mémoire et ce qu’il reste de votre quota :

- Le temps vient de vos propres générations passées sur ce poste, avec le même preset, le même moteur et la même résolution. Il affiche « — » s’il n’y en a pas encore.
- La mémoire est une estimation d’après la taille des fichiers de modèle, jamais une garantie.
- Le quota est vos **minutes GPU Video Producer** mensuelles. Un moteur cloud n’en consomme pas. Seuls les admins voient le coût d’une génération cloud.

Ce qui bloque **Générer la sélection** :

- aucune plage valide ;
- ni direction globale ni instruction locale dans la plage ;
- une instruction locale vide dans la plage ;
- le profil FL2VA sans frame de départ ni d’arrivée ;
- un quota épuisé.

Ce qui avertit seulement, sans bloquer : une estimation de mémoire supérieure à celle du moteur. L’avertissement indique que les poids passeront par la RAM de l’hôte, plus lentement, et la génération continue.

Pendant une génération, la barre affiche l’étape et la progression, avec **Annuler**.

Disponible à partir de l’étape 4.

## 7. Prises et final

Une prise est une vidéo générée pour un plan.

- Les brouillons sont faits à la résolution choisie par votre admin (832×480 sauf changement). La cadence d’une prise est imposée par le preset (Wan 16 i/s, MiniMax-H3 24 i/s). La timeline et les exports utilisent la cadence du projet.
- Plusieurs variantes sont faites par plan : A, B, etc. Cliquez sur l’icône en forme d’œil pour en prévisualiser une dans le visualiseur, et utilisez **Comparer** sur deux prises pour les voir côte à côte.
- **Utiliser** fait de la prise celle que le plan joue ; elle affiche alors **Utilisée**. **À reprendre** signale une prise à refaire. **Instructions utilisées** montre les instructions exactes d’une prise.
- **Final** sur une prise brouillon la passe en final. Par défaut, la prise est agrandie avec SeedVR2, en 720p, 1080p, 1440p ou 2160p. **Re-render**, l’action secondaire, génère le plan à nouveau à la résolution maximale du preset, avec la même graine. La nouvelle prise indique celle dont elle vient (« depuis A »).

Disponible à partir de l’étape 4.

## 8. Assistant

Le bouton **Assistant**, **Fenêtre › Assistant PotionUI** et ⌘ J ouvrent le chat PotionUI dans une fenêtre au-dessus de la page, en mode **Video Producer**. L’assistant peut :

- écrire l’instruction du plan sélectionné ;
- corriger les contradictions entre la direction globale et les instructions locales ;
- découper votre synopsis en plans ;
- vérifier la continuité entre les plans.

Chaque modification du projet demande votre approbation avant d’être appliquée. L’assistant connaît l’espace où vous êtes, votre sélection, la tête de lecture, la plage, la direction globale, le synopsis et l’état de la production. Il faut que votre admin ait configuré un modèle de langage.

Disponible à partir de l’étape 5.

## 9. Prompts : bibliothèque et compositeur

La fenêtre **Bibliothèque & assistant de prompts** s’ouvre par **Fenêtre › Bibliothèque de prompts**, ou par les boutons **Bibliothèque & assistant** placés près d’un texte. Elle écrit dans une cible : l’un des cinq champs de la direction globale, ou une instruction locale.

- **Bibliothèque.** Cinq bibliothèques, **Intégrée**, **Personnelle**, **Projet**, **Favoris** et **Historique**, et neuf catégories (Cinéma, Caméra, Éclairage, Styles cinématographiques, Dialogue, Photographie, Son, Continuité, À éviter). Un gabarit peut avoir des variables, comme le sujet ou le lieu, que vous remplissez avant de l’insérer.
- **Compositeur.** Construit un prompt à partir de quatre parties, **Mouvement de caméra**, **Éclairage**, **Style cinématographique** et **Dialogue ou intention de jeu**, pour le profil H3 du projet.
- **Compléter le texte** ajoute au texte existant ; **Remplacer** le remplace.

Les trois profils H3 et ce que chacun demande sur la plage :

| Profil | Sens | Il demande |
|---|---|---|
| FL2VA | Continuité entre les images de départ et d’arrivée. | Des frames de départ et d’arrivée sur la plage. |
| Ref2VA | Préserver l’identité des références pendant l’action. | Une référence d’identité (personnage, objet). Avec MiniMax-H3, la génération suit réellement les références. |
| Hybrid AV | La bande son, le rythme et le dialogue guident l’image. | Une piste audio sur la plage (dialogue ou musique). |

Quand une Control video est présente, le mouvement vient du guide.

Disponible à partir de l’étape 2.

## 10. Couleur et continuité

Une alerte n’apparaît que lorsque deux plans voisins ne se raccordent pas : « “Plan” est plus clair, plus sombre, plus chaud ou plus froid que le plan précédent ». **Raccorder** corrige en un clic, en ajustant l’exposition et la température sur celles du plan précédent. La mesure est faite sur les vraies vignettes des prises. L’onglet **Couleur** contient aussi le scope de luminance, six préréglages (Original, Lumière dorée, Matin froid, Film 35 mm, Nuit bleue, Doux) et des réglages fins (**Exposition**, **Contraste**, **Saturation**, **Température**), avec **Réinitialiser** et **À tous les plans**.

Le pourcentage d’identité que le prototype affichait entre deux plans est simulé (chapitre 15). La couleur, elle, est réelle.

Disponible à partir de l’étape 6.

## 11. Audio et sous-titres

L’audio vit dans des pistes, chacune avec un rôle : Dialogue, Musique, Ambiance ou SFX. **Audio › Ajouter une piste audio** et **Audio › Importer un fichier audio…** font entrer des sons ; **Audio › Console de mixage** affiche la console. **Voix et dialogues…** et les commandes de sound design ouvrent l’atelier, qui est simulé (chapitre 15). Le texte d’un dialogue, lui, est réel : il alimente les sous-titres, avec les titres de la timeline.

Disponible à partir de l’étape 3.

## 12. Exports

**Fichier › Exporter la vidéo…** ouvre **Exporter et partager**, avec trois onglets :

- **Vidéo.** Choisissez un format, une résolution et l’étendue (la séquence entière ou la plage). Les fichiers H.264 MP4 et VP9 WebM sont réellement assemblés. ProRes 422, H.265 et les stems audio sont marqués simulés.
- **Vers un autre logiciel.** Final Cut Pro (`.fcpxml`), OpenTimelineIO (`.otio`) et EDL CMX 3600 (`.edl`). Ce sont de vrais fichiers.
- **Sous-titres.** Un fichier SRT construit à partir du texte des dialogues et des titres.

Avant l’export, la fenêtre signale les plans qui ne sont pas encore en version finale, les prises marquées **À reprendre** et les contradictions de direction non résolues. Les exports sont écrits dans votre stockage PotionUI, dans un dossier `video_producer/exports/`, et vous les téléchargez depuis la page. Votre admin fixe un budget de taille pour ce dossier, par utilisateur.

Disponible à partir de l’étape 6.

## 13. Langue

Choisissez **English** ou **Français** dans **Video Producer › Préférences…**, ou cliquez sur le rappel `EN` ou `FR` de la barre d’état. Le changement est immédiat et n’est enregistré que pour vous. Il traduit l’interface et les messages ; vos propres textes (synopsis, direction, prompts, noms que vous avez saisis) ne sont jamais traduits.

Disponible à partir de l’étape 2.

## 14. Raccourcis clavier

⌘ est Commande sur un Mac et Ctrl ailleurs. **Rechercher une commande…** (⌘ K) trouve toutes les commandes, et **Raccourcis clavier** les liste. Ce tableau liste les raccourcis qui fonctionnent ; un raccourci affiché dans un menu mais absent d’ici peut ne pas encore être actif.

| Raccourci | Action |
|---|---|
| ⌘ K | Rechercher une commande |
| Échap | Fermer la palette, une fenêtre, l’assistant ou un menu ; sinon désélectionner |
| ⌘ Z, ⇧ ⌘ Z | Annuler, rétablir |
| ⌘ S | Enregistrer |
| ⌘ B | Couper à la tête de lecture |
| ⌘ D | Dupliquer |
| ⌘ G | Générer la sélection |
| ⌘ E, ⇧ ⌘ E | Exporter la vidéo…, Exporter vers un autre logiciel… |
| ⌘ I | Importer des fichiers… |
| ⌘ J | Assistant PotionUI |
| ⌃ ⌘ 1 | Panneau latéral |
| Espace | Lecture, pause |
| A, R, B | Outil Sélection, Outil Sélection de plage, Outil Lame |
| M | Ajouter un marqueur |
| I, O | Définir le point d’entrée, définir le point de sortie |
| N | Magnétisme |
| ⌫ | Supprimer |
| ← → | Une image en arrière ou en avant (une seconde avec Maj) |
| Home | Aller au début |

Disponible à partir de l’étape 2. Le tableau est confirmé sur le plugin à la dernière étape.

## 15. Ce qui est simulé

Certaines parties gardent leur interface mais ne font pas encore la vraie chose. Elles portent un badge gris pointillé, **Simulé**, jamais jaune : le jaune est réservé aux vrais points à vérifier. **Aide › Fonctions simulées** ouvre la liste.

**Réel dans Video Producer**

| Quoi | Comment cela fonctionne |
|---|---|
| **Génération.** | Les prises sont de vrais fichiers vidéo produits par le moteur choisi (ce poste, un serveur d’atelier ou un modèle cloud). La progression et les erreurs viennent du moteur. L’estimation indique le temps GPU (d’après vos propres générations ici, « — » s’il n’y en a pas), la mémoire, votre quota mensuel et, pour les admins seulement, le coût cloud. |
| **Finaliser une prise.** | **Final** agrandit la prise choisie avec SeedVR2 par défaut. **Re-render** (action secondaire) la régénère à la résolution maximale du preset avec la même graine. |
| **Assistant.** | Le chat PotionUI en mode Video Producer écrit les instructions de plan, corrige les contradictions avec la direction globale, découpe un synopsis en plans et vérifie la continuité. Vous approuvez chaque changement avant qu’il touche le projet. |
| **Génération guidée par références.** | Avec MiniMax-H3, le profil Ref2VA conditionne réellement la génération sur vos références. |
| **Médias et projets.** | L’import passe par les sélecteurs de PotionUI, la galerie montre vos propres médias, les projets sont enregistrés, les vignettes et la lecture vidéo sont celles des vrais fichiers. |
| **Couleur.** | Le raccord de couleur est mesuré sur les vraies vignettes. |
| **Mixage.** | La console joue vos vrais fichiers audio : faders, mute et solo, panoramique, égaliseur, compresseur, envois et vumètres. |
| **Export.** | Les vidéos H.264 MP4 et VP9 WebM assemblées avec ffmpeg, le XML Final Cut Pro, OpenTimelineIO, l’EDL et les sous-titres SRT sont de vrais fichiers. |
| **Sous-titres.** | Le texte des dialogues et des titres alimente le fichier SRT. |

**Toujours simulé, et pourquoi**

| Quoi | Pourquoi |
|---|---|
| **Réglages du moteur sans équivalent dans le preset choisi** : `hybrid`, `profiles`, `consistency`, `lockIdentity`, `motionPriority`, `offset`, `followCut`, `guidance`, `overlap`, `windowLen`, `loras`, `post.*`, `audioDriver`, `lipSync`, `naming`, `autoInsert`, `quality`. | Un preset n’expose que les contrôles qu’il déclare ; MiniMax-H3, par exemple, n’a ni guidage ni prompt négatif. Ils restent visibles, grisés et marqués simulés. |
| **Mesure d’identité entre plans.** | Le raccord de couleur est mesuré sur les vraies images ; le pourcentage de ressemblance entre deux plans ne l’est pas, car aucune mesure d’identité n’est offerte aux plugins. |
| **Synchronisation labiale et voix générées.** | Personnage, timbre et texte ne produisent pas encore de parole, et la synchronisation labiale n’a pas d’étape séparée (MiniMax-H3 fait image et son en une passe). Le texte du dialogue alimente bien les sous-titres. |
| **Atelier Sound design hors voix** : Ambiance, Bruitage, Texture, Impact, Musique. | Aucun preset ne prépare encore ces sons : l’atelier ne fait que simuler la préparation. |
| **ProRes, H.265 et stems audio.** | Le convertisseur vidéo de PotionUI n’écrit que du H.264 MP4 ou du WebM VP9, et aucun rendu audio par rôle n’existe. |
| **Courbes d’automation de la console.** | Le bouton Auto ne change qu’un mode ; aucune courbe n’est enregistrée. |
| **Scène 3D.** | La caméra, les positions clés et les trajectoires fonctionnent, mais la scène reste un aperçu de points en 2D ; les fichiers Gaussian Splat sont référencés sans être chargés ; la vidéo de guide n’est pas rendue. |
| **Capture 3D et Control video importée.** | Elles gardent le comportement du prototype : la capture n’est pas rendue depuis la scène 3D et la Control video importée n’est envoyée à aucun moteur. |
| **Modes de production Rendu 3D et Rendu 3D + IA.** | Ils dépendent de la vidéo de guide de la scène 3D, qui n’est pas rendue. |

## 16. Dépannage

- **La barre Production n’affiche aucun moteur.** Votre admin n’a pas terminé la mise en place : un moteur, un preset vidéo qui vous est attribué. Demandez-lui d’ouvrir Admin → Plugins → Video Producer.
- **L’estimation affiche « — » pour le temps.** Rien n’a encore été mesuré pour ce preset, ce moteur et cette résolution sur ce poste. Elle se remplit après quelques générations.
- **Les poids passeront par la RAM de l’hôte, plus lentement.** L’estimation de mémoire dépasse celle du moteur. La génération n’est pas bloquée. Si le serveur manque de mémoire libre pour cela, le moteur refuse de démarrer et la prise échoue avec une erreur.
- **Le quota est épuisé.** **Générer la sélection** est refusé jusqu’au mois suivant ou jusqu’à ce que votre admin relève la limite de votre plan. Les générations en cours ne sont pas arrêtées.
- **Générer la sélection est désactivé.** Lisez le message de la barre : pas de plage, ni direction ni instruction locale, une instruction vide, le profil FL2VA sans frame de départ ni d’arrivée, ou le quota.
- **Les références sont ignorées avec MiniMax-H3.** Demandez à votre admin de vérifier le fichier de modèle choisi pour le mode Références.
- **Une prise a échoué.** Le message et son code sont affichés sur la prise. Si PotionUI a redémarré pendant la génération, la prise est marquée en échec et la génération ne peut pas reprendre : relancez-la.
- **Un export échoue.** Interrogez votre admin sur ffmpeg, ou libérez de la place dans vos exports : le dossier a un budget de taille.

Disponible à partir de l’étape 4. Les exports à partir de l’étape 6.

## 17. Glossaire

| Français | English | Sens |
|---|---|---|
| plan | shot | Un morceau du film, une génération. |
| prise | take | Une version générée d’un plan. |
| brouillon | draft | Une prise rapide, en résolution réduite, pour juger le mouvement et le cadrage. |
| final | final | La prise retenue, agrandie ou régénérée. |
| raccord | match | Faire se ressembler deux plans voisins (couleur) ou garder la même identité. |
| fondu | fade | Un début ou une fin progressive d’un clip. |
| tête de lecture | playhead | La position courante sur la timeline. |
| plage | range | Une partie de la timeline entre un point d’entrée et un point de sortie. |
| direction globale | global direction | Le texte qui guide toutes les générations. |
| instruction locale | shot prompt | Le texte d’un plan ; il complète la direction globale. |
| Control video | Control video | Une vidéo de guide qui impose le mouvement. |
| profil H3 | H3 profile | FL2VA, Ref2VA ou Hybrid AV : ce qui guide la génération. |
