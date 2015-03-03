//
//  ViewController.m
//  D&D Player Sheet
//
//  Created by Adam on 10/02/2015.
//  Copyright (c) 2015 Adam. All rights reserved.
//

#import "ViewController.h"

float hitPoints;
float maxHitPointsVar;
float divided;


@interface ViewController ()

@end

@implementation ViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    NSString *loadHitPoints = [defaults objectForKey:@"currentHitPoints"];
    
    [currentHitPoints setText: [defaults objectForKey:@"currentHitPoints"]];
    hitPoints = [loadHitPoints intValue];
    // Do any additional setup after loading the view, typically from a nib.
    [NSTimer scheduledTimerWithTimeInterval:10.0 target:self selector:@selector(runTimer) userInfo:nil repeats:true];
    [self loadData];
    
    //maxHitPointsVar = [maxHitPoints.text floatValue];
    //divided = hitPoints/maxHitPointsVar;
   // [hitPointsSlider setProgress:divided];
    }

- (void)didReceiveMemoryWarning {
    [super didReceiveMemoryWarning];
    // Dispose of any resources that can be recreated.
}

-(void)runTimer
{
    [self saveData:self];
}

-(IBAction)hitPointsUp:(id)sender
{
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    
    hitPoints ++;
    [currentHitPoints setText:[NSString stringWithFormat:@"%d", [@(hitPoints) intValue]]];
    [defaults setObject:currentHitPoints.text forKey:@"currentHitPoints"];
    [defaults synchronize];
    
    maxHitPointsVar = [maxHitPoints.text floatValue];
    divided = hitPoints/maxHitPointsVar;
    [hitPointsSlider setProgress:divided];
    
    
}

-(IBAction)hitPointsDown:(id)sender
{
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    
    hitPoints --;
    [currentHitPoints setText:[NSString stringWithFormat:@"%d", [@(hitPoints) intValue]]];
    [defaults setObject:currentHitPoints.text forKey:@"currentHitPoints"];
    [defaults synchronize];
    
    maxHitPointsVar = [maxHitPoints.text floatValue];
    divided = hitPoints/maxHitPointsVar;
    [hitPointsSlider setProgress:divided];
    
}

-(IBAction)hitPointsChanged:(id)sender
{
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    
    hitPoints = [currentHitPoints.text floatValue];
    [defaults setObject:currentHitPoints.text forKey:@"currentHitPoints"];
    [defaults synchronize];
    
    maxHitPointsVar = [maxHitPoints.text floatValue];
    divided = hitPoints/maxHitPointsVar;
    [hitPointsSlider setProgress:divided];
    
}


-(IBAction)saveData:(id)sender {
   
   NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    
    [defaults setObject:charName.text forKey:@"charName"];
    [defaults setObject:race.text forKey:@"race"];
    [defaults setObject:playerName.text forKey:@"playerName"];
    [defaults setObject:charClass.text forKey:@"charClass"];
    [defaults setObject:background.text forKey:@"background"];
    [defaults setObject:alignment.text forKey:@"alignment"];
    [defaults setObject:xp.text forKey:@"xp"];
    [defaults setObject:profBonus.text forKey:@"profBonus"];
    [defaults setObject:inspiration.text forKey:@"inspiration"];
    [defaults setObject:armourClass.text forKey:@"armourClass"];
    [defaults setObject:initiative.text forKey:@"initiative"];
    [defaults setObject:speed.text forKey:@"speed"];
    [defaults setObject:maxHitPoints.text forKey:@"maxHitPoints"];
    [defaults setObject:currentHitPoints.text forKey:@"currentHitPoints"];
    [defaults setObject:hitDice.text forKey:@"hitDice"];
    [defaults setObject:hitDiceTotal.text forKey:@"hitDiceTotal"];
    [defaults setObject:tempHitPoints.text forKey:@"tempHitPoints"];
    [defaults setObject:weaponName1.text forKey:@"weaponName1"];
    [defaults setObject:weaponName2.text forKey:@"weaponName2"];
    [defaults setObject:weaponName3.text forKey:@"weaponName3"];
    [defaults setObject:attackBonus1.text forKey:@"attackBonus1"];
    [defaults setObject:attackBonus2.text forKey:@"attackBonus2"];
    [defaults setObject:attackBonus3.text forKey:@"attackBonus3"];
    [defaults setObject:damageType1.text forKey:@"damageType1"];
    [defaults setObject:damageType2.text forKey:@"damageType2"];
    [defaults setObject:damageType3.text forKey:@"damageType3"];
    [defaults setObject:strength.text forKey:@"strength"];
    [defaults setObject:strengthProf.text forKey:@"strengthProf"];
    [defaults setObject:dexterity.text forKey:@"dexterity"];
    [defaults setObject:dextreityProf.text forKey:@"dexterityProf"];
    [defaults setObject:constitution.text forKey:@"constitution"];
    [defaults setObject:constitutionProf.text forKey:@"constitutionProf"];
    [defaults setObject:intelligence.text forKey:@"intelligence"];
    [defaults setObject:intelligenceProf.text forKey:@"intelligenceProf"];
    [defaults setObject:wisdom.text forKey:@"wisdom"];
    [defaults setObject:wisdomProf.text forKey:@"wisdomProf"];
    [defaults setObject:charisma.text forKey:@"charisma"];
    [defaults setObject:charismaProf.text forKey:@"charismaProf"];
    [defaults setObject:passiveWisdom.text forKey:@"passiveWisdom"];
    [defaults setObject:spellDetails.text forKey:@"spellDetails"];
    [defaults setObject:profLanguages.text forKey:@"profLanguages"];
    [defaults setObject:featTraits.text forKey:@"featTraits"];
    [defaults setObject:equipNotes.text forKey:@"equipNotes"];
    [defaults setBool:strSavingThrow.on forKey:@"strSavingThrow"];
    [defaults setBool:athletics.on forKey:@"athletics"];
    [defaults setBool:dexSavingThrow.on forKey:@"dexSavingThrow"];
    [defaults setBool:stealth.on forKey:@"stealth"];
    [defaults setBool:acrobatics.on forKey:@"acrobatics"];
    [defaults setBool:sleightOfHand.on forKey:@"sleightOfHand"];
    [defaults setBool:constSavingThrow.on forKey:@"constSavingThrow"];
    [defaults setBool:intelSavingThrow.on forKey:@"intelSavingThrow"];
    [defaults setBool:investigation.on forKey:@"investigation"];
    [defaults setBool:arcana.on forKey:@"arcana"];
    [defaults setBool:nature.on forKey:@"nature"];
    [defaults setBool:history.on forKey:@"history"];
    [defaults setBool:religion.on forKey:@"religion"];
    [defaults setBool:wisdomSavingThrow.on forKey:@"wisdomSavingThrow"];
    [defaults setBool:medicine.on forKey:@"medicine"];
    [defaults setBool:perceptionSwitch.on forKey:@"perceptionSwitch"];
    [defaults setBool:animalHandling.on forKey:@"animalHandling"];
    [defaults setBool:insight.on forKey:@"insight"];
    [defaults setBool:survival.on forKey:@"survival"];
    [defaults setBool:charSavingThrow.on forKey:@"charSavingThrow"];
    [defaults setBool:performance.on forKey:@"performance"];
    [defaults setBool:deception.on forKey:@"deception"];
    [defaults setBool:persuasion.on forKey:@"persuasion"];
    [defaults setBool:intimidation.on forKey:@"intimidation"];
    
    
    [defaults synchronize];
    
    maxHitPointsVar = [maxHitPoints.text floatValue];
    divided = hitPoints/maxHitPointsVar;
    [hitPointsSlider setProgress:divided];
    
    NSLog(@"Data Saved Successfully!");
}

-(void)loadData {
    
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    
    [charName setText:[defaults objectForKey:@"charName"]];
    [race setText:[defaults objectForKey:@"race"]];
    [playerName setText:[defaults objectForKey:@"playerName"]];
    [charClass setText:[defaults objectForKey:@"charClass"]];
    [background setText:[defaults objectForKey:@"background"]];
    [alignment setText:[defaults objectForKey:@"alignment"]];
    [xp setText:[defaults objectForKey:@"xp"]];
    [profBonus setText:[defaults objectForKey:@"profBonus"]];
    [inspiration setText:[defaults objectForKey:@"inspiration"]];
    [armourClass setText:[defaults objectForKey:@"armourClass"]];
    [initiative setText:[defaults objectForKey:@"initiative"]];
    [speed setText:[defaults objectForKey:@"speed"]];
    [maxHitPoints setText:[defaults objectForKey:@"maxHitPoints"]];
    //[defaults objectForKey:@"currentHitPoints"]];
    [hitDice setText:[defaults objectForKey:@"hitDice"]];
    [hitDiceTotal setText:[defaults objectForKey:@"hitDiceTotal"]];
    [tempHitPoints setText:[defaults objectForKey:@"tempHitPoints"]];
    [weaponName1 setText:[defaults objectForKey:@"weaponName1"]];
    [weaponName2 setText:[defaults objectForKey:@"weaponName2"]];
    [weaponName3 setText:[defaults objectForKey:@"weaponName3"]];
    [attackBonus1 setText:[defaults objectForKey:@"attackBonus1"]];
    [attackBonus2 setText:[defaults objectForKey:@"attackBonus2"]];
    [attackBonus3 setText:[defaults objectForKey:@"attackBonus3"]];
    [damageType1 setText:[defaults objectForKey:@"damageType1"]];
    [damageType2 setText:[defaults objectForKey:@"damageType2"]];
    [damageType3 setText:[defaults objectForKey:@"damageType3"]];
    [strength setText:[defaults objectForKey:@"strength"]];
    [strengthProf setText:[defaults objectForKey:@"strengthProf"]];
    [dexterity setText:[defaults objectForKey:@"dexterity"]];
    [dextreityProf setText:[defaults objectForKey:@"dexterityProf"]];
    [constitution setText:[defaults objectForKey:@"constitution"]];
    [constitutionProf setText:[defaults objectForKey:@"constitutionProf"]];
    [intelligence setText:[defaults objectForKey:@"intelligence"]];
    [intelligenceProf setText:[defaults objectForKey:@"intelligenceProf"]];
    [wisdom setText:[defaults objectForKey:@"wisdom"]];
    [wisdomProf setText:[defaults objectForKey:@"wisdomProf"]];
    [charisma setText:[defaults objectForKey:@"charisma"]];
    [charismaProf setText:[defaults objectForKey:@"charismaProf"]];
    [passiveWisdom setText:[defaults objectForKey:@"passiveWisdom"]];
    [spellDetails setText:[defaults objectForKey:@"spellDetails"]];
    [profLanguages setText:[defaults objectForKey:@"profLanguages"]];
    [featTraits setText:[defaults objectForKey:@"featTraits"]];
    [equipNotes setText:[defaults objectForKey:@"equipNotes"]];
    //[defaults synchronize];
    [strSavingThrow setOn:[defaults boolForKey:@"strSavingThrow"]];
    [athletics setOn:[defaults boolForKey:@"athletics"]];
    [dexSavingThrow setOn:[defaults boolForKey:@"dexSavingThrow"]];
    [stealth setOn:[defaults boolForKey:@"stealth"]];
    [acrobatics setOn:[defaults boolForKey:@"acrobatics"]];
    [sleightOfHand setOn:[defaults boolForKey:@"sleightOfHand"]];
    [constSavingThrow setOn:[defaults boolForKey:@"constSavingThrow"]];
    [intelSavingThrow setOn:[defaults boolForKey:@"intelSavingThrow"]];
    [investigation setOn:[defaults boolForKey:@"investigation"]];
    [arcana setOn:[defaults boolForKey:@"arcana"]];
    [nature setOn:[defaults boolForKey:@"nature"]];
    [history setOn:[defaults boolForKey:@"history"]];
    [religion setOn:[defaults boolForKey:@"religion"]];
    [wisdomSavingThrow setOn:[defaults boolForKey:@"wisdomSavingThrow"]];
    [medicine setOn:[defaults boolForKey:@"medicine"]];
    [perceptionSwitch setOn:[defaults boolForKey:@"perceptionSwitch"]];
    [animalHandling setOn:[defaults boolForKey:@"animalHandling"]];
    [insight setOn:[defaults boolForKey:@"insight"]];
    [survival setOn:[defaults boolForKey:@"survival"]];
    [charSavingThrow setOn:[defaults boolForKey:@"charSavingThrow"]];
    [performance setOn:[defaults boolForKey:@"performance"]];
    [deception setOn:[defaults boolForKey:@"deception"]];
    [persuasion setOn:[defaults boolForKey:@"persuasion"]];
    [intimidation setOn:[defaults boolForKey:@"intimidation"]];

    maxHitPointsVar = [maxHitPoints.text floatValue];
    divided = hitPoints/maxHitPointsVar;
    [hitPointsSlider setProgress:divided];
    
    [self switchedSwitch:self];
    NSLog(@"Data Loaded Successfully!");
}

-(IBAction)switchedSwitch:(id)sender
{
    if (strSavingThrow.on) {
        [strsavelbl setText:[NSString stringWithFormat:@"+%d",([strength.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [strsavelbl setText:[NSString stringWithFormat:@"+%@",strengthProf.text ]];
    }
    
    if (athletics.on) {
        [athleticslbl setText:[NSString stringWithFormat:@"+%d",([strength.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [athleticslbl setText:[NSString stringWithFormat:@"+%@",strengthProf.text ]];
    }


    if (dexSavingThrow.on) {
        [dexsavelbl setText:[NSString stringWithFormat:@"+%d",([dexterity.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [dexsavelbl setText:[NSString stringWithFormat:@"+%@",dextreityProf.text ]];
    }


    if (acrobatics.on) {
        [acrobaticslbl setText:[NSString stringWithFormat:@"+%d",([dexterity.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [acrobaticslbl setText:[NSString stringWithFormat:@"+%@",dextreityProf.text ]];
    }


    if (sleightOfHand.on) {
        [sleightofhandlbl setText:[NSString stringWithFormat:@"+%d",([dexterity.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [sleightofhandlbl setText:[NSString stringWithFormat:@"+%@",dextreityProf.text ]];
    }


    if (stealth.on) {
        [stealthlbl setText:[NSString stringWithFormat:@"+%d",([dexterity.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [stealthlbl setText:[NSString stringWithFormat:@"+%@",dextreityProf.text ]];
    }


    if (constSavingThrow.on) {
        [constsavelbl setText:[NSString stringWithFormat:@"+%d",([constitution.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [constsavelbl setText:[NSString stringWithFormat:@"+%@",constitutionProf.text ]];
    }


    if (intelSavingThrow.on) {
        [intelsavelbl setText:[NSString stringWithFormat:@"+%d",([intelligence.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [intelsavelbl setText:[NSString stringWithFormat:@"+%@",intelligenceProf.text ]];
    }


    if (arcana.on) {
        [arcanalbl setText:[NSString stringWithFormat:@"+%d",([intelligence.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [arcanalbl setText:[NSString stringWithFormat:@"+%@",intelligenceProf.text ]];
    }


    if (history.on) {
        [historylbl setText:[NSString stringWithFormat:@"+%d",([intelligence.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [historylbl setText:[NSString stringWithFormat:@"+%@",intelligenceProf.text ]];
    }


    if (investigation.on) {
        [investigationlbl setText:[NSString stringWithFormat:@"+%d",([intelligence.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [investigationlbl setText:[NSString stringWithFormat:@"+%@",intelligenceProf.text ]];
    }


    if (nature.on) {
        [naturelbl setText:[NSString stringWithFormat:@"+%d",([intelligence.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [naturelbl setText:[NSString stringWithFormat:@"+%@",intelligenceProf.text ]];
    }


    if (religion.on) {
        [religionlbl setText:[NSString stringWithFormat:@"+%d",([intelligence.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [religionlbl setText:[NSString stringWithFormat:@"+%@",intelligenceProf.text ]];
    }


    if (wisdomSavingThrow.on) {
        [wisdomsavelbl setText:[NSString stringWithFormat:@"+%d",([wisdom.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [wisdomsavelbl setText:[NSString stringWithFormat:@"+%@",wisdomProf.text ]];
    }


    if (perceptionSwitch.on) {
        [perceptionlbl setText:[NSString stringWithFormat:@"+%d",([wisdom.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [perceptionlbl setText:[NSString stringWithFormat:@"+%@",wisdomProf.text ]];
    }


    if (animalHandling.on) {
        [animallbl setText:[NSString stringWithFormat:@"+%d",([wisdom.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [animallbl setText:[NSString stringWithFormat:@"+%@",wisdomProf.text ]];
    }


    if (medicine.on) {
        [medicinelbl setText:[NSString stringWithFormat:@"+%d",([wisdom.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [medicinelbl setText:[NSString stringWithFormat:@"+%@",wisdomProf.text ]];
    }


    if (insight.on) {
        [insightlbl setText:[NSString stringWithFormat:@"+%d",([wisdom.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [insightlbl setText:[NSString stringWithFormat:@"+%@",wisdomProf.text ]];
    }


    if (survival.on) {
        [survivallbl setText:[NSString stringWithFormat:@"+%d",([wisdom.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [survivallbl setText:[NSString stringWithFormat:@"+%@",wisdomProf.text ]];
    }


    if (charSavingThrow.on) {
        [charsavelbl setText:[NSString stringWithFormat:@"+%d",([charisma.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [charsavelbl setText:[NSString stringWithFormat:@"+%@",charismaProf.text ]];
    }


    if (deception.on) {
        [deceptionlbl setText:[NSString stringWithFormat:@"+%d",([charisma.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [deceptionlbl setText:[NSString stringWithFormat:@"+%@",charismaProf.text ]];
    }


    if (intimidation.on) {
        [intimidationlbl setText:[NSString stringWithFormat:@"+%d",([charisma.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [intimidationlbl setText:[NSString stringWithFormat:@"+%@",charismaProf.text ]];
    }


    if (performance.on) {
        [performancelbl setText:[NSString stringWithFormat:@"+%d",([charisma.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [performancelbl setText:[NSString stringWithFormat:@"+%@",charismaProf.text ]];
    }


    if (persuasion.on) {
        [persuasionlbl setText:[NSString stringWithFormat:@"+%d",([charisma.text intValue] - 10) / 2 + [profBonus.text intValue]]];
    }
    else
    {
        [persuasionlbl setText:[NSString stringWithFormat:@"+%@",charismaProf.text ]];
    }


    
}

-(IBAction)editValue:(id)sender
{
    [strengthProf setText:[NSString stringWithFormat:@"%d",([strength.text intValue] - 10) / 2] ];
    [dextreityProf setText:[NSString stringWithFormat:@"%d",([dexterity.text intValue] - 10) / 2] ];
    [constitutionProf setText:[NSString stringWithFormat:@"%d",([constitution.text intValue] - 10) / 2] ];
    [intelligenceProf setText:[NSString stringWithFormat:@"%d",([intelligence.text intValue] - 10) / 2] ];
    [wisdomProf setText:[NSString stringWithFormat:@"%d",([wisdom.text intValue] - 10) / 2] ];
    [charismaProf setText:[NSString stringWithFormat:@"%d",([charisma.text intValue] - 10) / 2] ];
}





@end
