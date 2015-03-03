//
//  ViewController.h
//  D&D Player Sheet
//
//  Created by Adam on 10/02/2015.
//  Copyright (c) 2015 Adam. All rights reserved.
//

#import <UIKit/UIKit.h>

@interface ViewController : UIViewController{
    
    IBOutlet UITextField *charName;
    IBOutlet UITextField *race;
    IBOutlet UITextField *playerName;
    IBOutlet UITextField *charClass;
    IBOutlet UITextField *background;
    IBOutlet UITextField *alignment;
    IBOutlet UITextField *xp;
    IBOutlet UITextField *profBonus;
    IBOutlet UITextField *inspiration;
    IBOutlet UITextField *armourClass;
    IBOutlet UITextField *initiative;
    IBOutlet UITextField *speed;
    IBOutlet UITextField *maxHitPoints;
    IBOutlet UITextField *currentHitPoints;
    IBOutlet UITextField *hitDice;
    IBOutlet UITextField *hitDiceTotal;
    IBOutlet UITextField *tempHitPoints;
    IBOutlet UITextField *weaponName1;
    IBOutlet UITextField *weaponName2;
    IBOutlet UITextField *weaponName3;
    IBOutlet UITextField *attackBonus1;
    IBOutlet UITextField *attackBonus2;
    IBOutlet UITextField *attackBonus3;
    IBOutlet UITextField *damageType1;
    IBOutlet UITextField *damageType2;
    IBOutlet UITextField *damageType3;
    IBOutlet UITextField *strength;
    IBOutlet UITextField *strengthProf;
    IBOutlet UITextField *dexterity;
    IBOutlet UITextField *dextreityProf;
    IBOutlet UITextField *constitution;
    IBOutlet UITextField *constitutionProf;
    IBOutlet UITextField *intelligence;
    IBOutlet UITextField *intelligenceProf;
    IBOutlet UITextField *wisdom;
    IBOutlet UITextField *wisdomProf;
    IBOutlet UITextField *charisma;
    IBOutlet UITextField *charismaProf;
    IBOutlet UITextField *passiveWisdom;
    IBOutlet UITextView *spellDetails;
    IBOutlet UITextView *profLanguages;
    IBOutlet UITextView *featTraits;
    IBOutlet UITextView *equipNotes;
    IBOutlet UIProgressView *hitPointsSlider;
    IBOutlet UISwitch *strSavingThrow, *athletics, *dexSavingThrow, *stealth, *acrobatics, *sleightOfHand, *constSavingThrow, *intelSavingThrow, *investigation, *arcana, *nature, *history, *religion, *wisdomSavingThrow, *medicine, *perceptionSwitch, *animalHandling, *insight, *survival, *charSavingThrow, *performance, *deception, *persuasion, *intimidation;
    IBOutlet UILabel *strsavelbl, *athleticslbl, *dexsavelbl, *acrobaticslbl, *sleightofhandlbl, *stealthlbl, *constsavelbl, *intelsavelbl, *arcanalbl, *historylbl, *investigationlbl, *naturelbl, *religionlbl, *wisdomsavelbl, *perceptionlbl, *animallbl, *medicinelbl, *insightlbl, *survivallbl, *charsavelbl, *deceptionlbl, *intimidationlbl, *performancelbl, *persuasionlbl;
    

}

-(IBAction)hitPointsUp:(id)sender;
-(IBAction)hitPointsDown:(id)sender;
-(IBAction)hitPointsChanged:(id)sender;
-(IBAction)saveData:(id)sender;
-(IBAction)switchedSwitch:(id)sender;
-(IBAction)editValue:(id)sender;

@end

